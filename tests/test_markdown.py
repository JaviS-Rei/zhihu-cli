"""Tests for Zhihu HTML to Markdown conversion."""

from __future__ import annotations

from zhihu_cli.markdown import html_to_markdown


class TestHtmlToMarkdown:
    def test_converts_basic_article_structure(self):
        html = (
            "<h2>一、标题</h2>"
            "<p>正文 <b>加粗</b> <code>x = 1</code></p>"
            "<ol><li>第一项</li><li>第二项</li></ol>"
        )

        result = html_to_markdown(html)

        assert "## 一、标题" in result.markdown
        assert "正文 **加粗** `x = 1`" in result.markdown
        assert "1. 第一项" in result.markdown
        assert "2. 第二项" in result.markdown
        assert result.unknown_tags == set()

    def test_uses_original_image_url(self):
        html = (
            '<figure><img src="thumb.jpg" data-original="full.jpg" '
            'data-caption="示意图"/></figure>'
        )

        result = html_to_markdown(html)

        assert "![示意图](full.jpg)" in result.markdown

    def test_decodes_zhihu_external_link_target(self):
        html = (
            '<a href="https://link.zhihu.com/?target=https%3A//example.com/a%3Fx%3D1">'
            "example</a>"
        )

        result = html_to_markdown(html)

        assert "[example](https://example.com/a?x=1)" in result.markdown

    def test_preserves_unknown_tags_and_reports_them(self):
        html = '<p>before</p><zhihu-card data-id="1">card</zhihu-card><p>after</p>'

        result = html_to_markdown(html)

        assert '<zhihu-card data-id="1">card</zhihu-card>' in result.markdown
        assert result.unknown_tags == {"zhihu-card"}
