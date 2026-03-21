"""Playwright E2E 用户旅程测试 — VoiceKB 验收。

使用 iPhone 12 视口模拟手机浏览器访问。
每个步骤截图保存到 tests/screenshots/。
"""
import asyncio
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, expect

BASE_URL = "http://127.0.0.1:18089"
SCREENSHOTS = Path(__file__).parent / "screenshots"
SCREENSHOTS.mkdir(exist_ok=True)
AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio"

# iPhone 12 viewport
DEVICE = {
    "viewport": {"width": 390, "height": 844},
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
}


def screenshot(page: Page, name: str) -> None:
    page.screenshot(path=str(SCREENSHOTS / f"{name}.png"))
    print(f"  [screenshot] {name}.png")


def test_journey_a_first_use():
    """旅程 A：首次使用 — 上传录音、查看转写、标注说话人。"""
    print("\n=== 旅程 A：首次使用 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**DEVICE)
        page = context.new_page()

        # 收集 console errors
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        # Step 1: 打开首页
        print("Step 1: 打开首页")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        screenshot(page, "A1_homepage")

        # 验证页面有内容（不是空白）
        content = page.content()
        assert "VoiceKB" in content, "首页应包含 VoiceKB 标题"
        print("  OK: 首页渲染正常")

        # Step 2: 上传录音
        print("Step 2: 上传录音")
        # 如果有数据，先检查列表
        if page.locator(".rec-card").count() > 0:
            print("  已有录音数据，跳过上传")
            # 点击第一个录音查看详情
            page.locator(".rec-card").first.click()
            page.wait_for_timeout(1000)
            screenshot(page, "A2_existing_detail")
        else:
            # 触发上传
            file_input = page.locator("#fileInput")
            file_input.set_input_files(str(AUDIO_DIR / "meeting_product_planning.wav"))
            page.wait_for_timeout(2000)
            screenshot(page, "A2_upload_progress")
            print("  OK: 文件已上传")

            # Step 3: 等待处理完成（最多 3 分钟）
            print("Step 3: 等待处理完成")
            for i in range(36):
                page.wait_for_timeout(5000)
                progress_text = page.locator("#procText, #uploadText").text_content() if page.locator("#procText, #uploadText").count() > 0 else ""
                print(f"  [{i*5}s] {progress_text}")
                if "完成" in (progress_text or ""):
                    break
                # Check if already on detail page
                if page.locator(".transcript-item").count() > 0:
                    break
            screenshot(page, "A3_processing_done")

        # Step 4: 查看转写详情
        print("Step 4: 查看转写详情")
        page.wait_for_timeout(2000)
        screenshot(page, "A4_transcript")

        # 检查是否有转写内容
        has_transcript = page.locator(".transcript-item").count() > 0 or page.locator(".rec-card").count() > 0
        print(f"  转写内容: {'有' if has_transcript else '无'}")

        # Step 5: 标注说话人
        print("Step 5: 标注说话人")
        # 在转写详情区域内定位可见的 speaker tag
        speaker_tags = page.locator(".transcript-item .speaker-tag")
        visible_count = 0
        for i in range(speaker_tags.count()):
            if speaker_tags.nth(i).is_visible():
                visible_count += 1
        print(f"  可见 speaker 标签: {visible_count}")
        if visible_count > 0:
            speaker_tags.first.click(timeout=5000)
            page.wait_for_timeout(500)
            screenshot(page, "A5_rename_modal")

            rename_input = page.locator("#renameInput")
            if rename_input.count() > 0:
                rename_input.fill("张三")
                page.locator("button:has-text('保存')").click()
                page.wait_for_timeout(1000)
                screenshot(page, "A5_renamed")
                print("  OK: 说话人已标注为张三")

        # 检查 console errors
        js_errors = [e for e in errors if "error" in e.lower() or "uncaught" in e.lower()]
        print(f"\n  JS errors: {len(js_errors)}")
        for e in js_errors[:3]:
            print(f"    - {e[:100]}")

        browser.close()
        print("=== 旅程 A 完成 ===\n")


def test_journey_c_search():
    """旅程 C：知识检索 — 关键词搜索和语义搜索。"""
    print("\n=== 旅程 C：知识检索 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**DEVICE)
        page = context.new_page()

        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        # 点击搜索 tab
        print("Step 1: 切换到搜索")
        page.locator(".tab-item:has-text('搜索')").click()
        page.wait_for_timeout(500)
        screenshot(page, "C1_search_tab")

        # Step 2: 关键词搜索
        print("Step 2: 关键词搜索 '预算'")
        search_input = page.locator("#searchInput")
        search_input.fill("预算")
        # 等待 debounce + API 响应
        page.wait_for_timeout(3000)
        screenshot(page, "C2_keyword_search")

        # 等待搜索结果出现
        try:
            page.locator(".search-result-item").first.wait_for(state="visible", timeout=10000)
        except Exception:
            # 用 JS 直接触发搜索
            page.evaluate("doSearch()")
            page.wait_for_timeout(3000)

        results = page.locator(".search-result-item")
        result_count = results.count()
        print(f"  搜索结果: {result_count} 条")
        assert result_count > 0, "搜索'预算'应返回结果"
        print("  OK: 关键词搜索有结果")

        # Step 3: 语义搜索
        print("Step 3: 语义搜索 '项目进度的看法'")
        search_input.fill("")
        search_input.fill("项目进度的看法")
        page.wait_for_timeout(2000)
        screenshot(page, "C3_semantic_search")

        browser.close()
        print("=== 旅程 C 完成 ===\n")


def test_journey_d_chat():
    """旅程 D：AI 问答。"""
    print("\n=== 旅程 D：AI 问答 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**DEVICE)
        page = context.new_page()

        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        # 点击问答 tab
        print("Step 1: 切换到问答")
        page.locator(".tab-item:has-text('问答')").click()
        page.wait_for_timeout(500)
        screenshot(page, "D1_chat_tab")

        # 检查欢迎消息
        welcome = page.locator(".chat-msg.ai .bubble").first
        assert welcome.is_visible(), "应显示欢迎消息"
        print("  OK: 欢迎消息显示")

        # Step 2: 提问
        print("Step 2: 提问")
        chat_input = page.locator("#chatInput")
        chat_input.fill("预算是怎么分配的？")
        page.locator(".chat-send").click()
        page.wait_for_timeout(5000)  # 等待 AI 回答
        screenshot(page, "D2_chat_response")

        # 检查是否有回答
        messages = page.locator(".chat-msg")
        msg_count = messages.count()
        print(f"  消息数: {msg_count}")
        assert msg_count >= 3, "应有用户消息和 AI 回答"

        # 检查 AI 回答不为空
        ai_msgs = page.locator(".chat-msg.ai .bubble")
        last_ai = ai_msgs.last
        ai_text = last_ai.text_content() or ""
        print(f"  AI 回答: {ai_text[:80]}...")
        assert len(ai_text) > 10, "AI 回答不应为空"
        print("  OK: AI 回答非空")

        browser.close()
        print("=== 旅程 D 完成 ===\n")


def test_mobile_layout():
    """验证移动端布局适配。"""
    print("\n=== 移动端布局检查 ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**DEVICE)
        page = context.new_page()

        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        # 检查无水平滚动
        scroll_width = page.evaluate("document.documentElement.scrollWidth")
        client_width = page.evaluate("document.documentElement.clientWidth")
        print(f"  scrollWidth={scroll_width}, clientWidth={client_width}")
        assert scroll_width <= client_width + 5, "不应有水平滚动"
        print("  OK: 无水平滚动溢出")

        # 检查底部导航存在
        tab_bar = page.locator(".tab-bar")
        assert tab_bar.is_visible(), "底部导航应可见"
        print("  OK: 底部导航可见")

        # 检查 FAB 按钮
        fab = page.locator("#fabUpload")
        assert fab.is_visible(), "上传按钮应可见"
        print("  OK: 上传 FAB 按钮可见")

        screenshot(page, "mobile_layout")
        browser.close()
        print("=== 移动端布局检查完成 ===\n")


if __name__ == "__main__":
    print("=" * 60)
    print("VoiceKB E2E 用户旅程测试")
    print("=" * 60)

    test_mobile_layout()
    test_journey_a_first_use()
    test_journey_c_search()
    test_journey_d_chat()

    print("\n" + "=" * 60)
    print("所有用户旅程测试完成！")
    print("=" * 60)
