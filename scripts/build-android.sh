#!/bin/bash
# VoiceKB Android APK 打包脚本
# 用法: ./scripts/build-android.sh
# 前置条件:
#   - Node.js (uni-app CLI)
#   - JDK 11 (Gradle 6.5 不支持 JDK 17+)
#   - Android SDK (platform-30, build-tools-30.0.3)
#   - pack-cli (npm install -g @xzcoder/pack-cli)
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIENT_DIR="$PROJECT_ROOT/client"
ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
JAVA_HOME="${JAVA_HOME:-/tmp/jdk-11.0.2}"

# ====== 颜色输出 ======
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[BUILD]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ====== 检查环境 ======
log "检查环境..."
command -v node >/dev/null || err "需要 Node.js"
[ -f "$JAVA_HOME/bin/java" ] || err "JAVA_HOME=$JAVA_HOME 不存在。需要 JDK 11"
[ -f "$ANDROID_HOME/platforms/android-30/android.jar" ] || err "需要 Android SDK platform-30"
[ -f "$ANDROID_HOME/build-tools/30.0.3/dx" ] || err "需要 Android build-tools 30.0.3"

# ====== Step 1: uni-app 编译 app 资源 ======
log "Step 1/4: 编译 uni-app app 资源..."
cd "$CLIENT_DIR"
NODE_PATH=$(dirname "$0")/../client/node_modules \
  node $(dirname "$0")/../client/node_modules/@dcloudio/vite-plugin-uni/bin/uni.js build -p app 2>&1 | tail -3

# pack-cli 硬编码寻找 app-plus 目录
rm -rf dist/build/app-plus
cp -r dist/build/app dist/build/app-plus

# ====== Step 2: 生成/检查 keystore ======
KEYSTORE="$CLIENT_DIR/voicekb.keystore"
if [ ! -f "$KEYSTORE" ]; then
  log "生成签名文件..."
  "$JAVA_HOME/bin/keytool" -genkey -v -keystore "$KEYSTORE" \
    -alias voicekb -keyalg RSA -keysize 2048 -validity 36500 \
    -storepass voicekb123 -keypass voicekb123 \
    -dname "CN=VoiceKB, OU=Dev, O=VoiceKB, L=Hangzhou, ST=Zhejiang, C=CN"
fi

# ====== Step 3: pack-cli 生成 Android 项目 + 配置 ======
log "Step 2/4: 生成 Android 项目..."

# 写配置文件
cat > "$CLIENT_DIR/pack.config.json" <<EOF
{
  "appPlusDist": "./dist/build/app-plus/",
  "android": {
    "sdk": "$ANDROID_HOME",
    "applicationId": "com.voicekb.app",
    "appKey": "",
    "keystore": {
      "file": "$KEYSTORE",
      "alias": "voicekb",
      "password": "voicekb123"
    }
  }
}
EOF

pack-cli --config pack.config.json 2>&1 || true

ANDROID_PROJECT="$CLIENT_DIR/dist/pack/uni-app-pack-android"

# ====== Step 3.5: 修复配置 ======
log "Step 3/4: 修复配置..."

# 修复 local.properties
echo "sdk.dir=$ANDROID_HOME" > "$ANDROID_PROJECT/local.properties"

# 修复 build.gradle — 阿里云镜像
cat > "$ANDROID_PROJECT/build.gradle" <<'GRADLE'
buildscript {
    repositories {
        maven { url 'https://maven.aliyun.com/repository/google' }
        maven { url 'https://maven.aliyun.com/repository/central' }
        maven { url 'https://maven.aliyun.com/repository/public' }
        google()
        mavenCentral()
    }
    dependencies {
        classpath 'com.android.tools.build:gradle:4.1.1'
    }
}
allprojects {
    repositories {
        maven { url 'https://maven.aliyun.com/repository/google' }
        maven { url 'https://maven.aliyun.com/repository/central' }
        maven { url 'https://maven.aliyun.com/repository/public' }
        google()
        mavenCentral()
    }
}
task clean(type: Delete) { delete rootProject.buildDir }
GRADLE

# 修复 gradle-wrapper.properties — 腾讯镜像
sed -i 's|https\\://services.gradle.org/distributions/|https\\://mirrors.cloud.tencent.com/gradle/|' \
  "$ANDROID_PROJECT/gradle/wrapper/gradle-wrapper.properties"

# 修复 app/build.gradle — buildToolsVersion
sed -i '/compileSdkVersion/a\    buildToolsVersion "30.0.3"' "$ANDROID_PROJECT/app/build.gradle"

# 复制 keystore（JDK 11 生成的）
cp "$KEYSTORE" "$ANDROID_PROJECT/app/keystore.jks"

# ====== Step 4: Gradle 构建 ======
log "Step 4/4: Gradle 构建 APK..."
cd "$ANDROID_PROJECT"
export ANDROID_HOME JAVA_HOME
./gradlew assembleRelease --no-daemon -x lintVitalRelease 2>&1 | tail -5

# ====== 输出 ======
APK="$ANDROID_PROJECT/app/build/outputs/apk/release/app-release.apk"
if [ -f "$APK" ]; then
  cp "$APK" "$PROJECT_ROOT/voicekb.apk"
  SIZE=$(ls -lh "$PROJECT_ROOT/voicekb.apk" | awk '{print $5}')
  log "构建成功！APK: $PROJECT_ROOT/voicekb.apk ($SIZE)"
  log "安装到手机: adb install $PROJECT_ROOT/voicekb.apk"
else
  err "APK 未生成，请检查上面的错误"
fi
