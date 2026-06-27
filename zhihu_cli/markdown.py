"""HTML to Markdown helpers for Zhihu rich text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class MarkdownResult:
    markdown: str
    unknown_tags: set[str]


_BLOCK_TAGS = {"p", "div", "section", "article", "blockquote", "figure"}
_INLINE_TAGS = {"span"}
_SKIP_TAGS = {"script", "style"}
_KNOWN_TAGS = {
    "a",
    "b",
    "br",
    "code",
    "del",
    "em",
    "figcaption",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "pre",
    "s",
    "strong",
    "u",
    "ul",
    *_BLOCK_TAGS,
    *_INLINE_TAGS,
    *_SKIP_TAGS,
}


def html_to_markdown(text: str | None) -> MarkdownResult:
    """Convert known Zhihu HTML tags to Markdown, preserving unknown tags."""
    if not text:
        return MarkdownResult("", set())
    parser = _ZhihuMarkdownParser()
    parser.feed(text)
    parser.close()
    return MarkdownResult(_cleanup_markdown(parser.output), parser.unknown_tags)


class _ZhihuMarkdownParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.unknown_tags: set[str] = set()
        self._list_stack: list[dict[str, int | str]] = []
        self._link_stack: list[str | None] = []
        self._skip_stack: list[str] = []

    @property
    def output(self) -> str:
        return "".join(self.parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        attr_dict = dict(attrs)
        if self._skip_stack:
            if tag in _SKIP_TAGS:
                self._skip_stack.append(tag)
            return
        if tag in _SKIP_TAGS:
            self._skip_stack.append(tag)
            return

        if tag not in _KNOWN_TAGS:
            self.unknown_tags.add(tag)
            self.parts.append(_format_start_tag(tag, attrs))
            return

        if tag in _BLOCK_TAGS:
            self._block_break()
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            self._block_break()
            self.parts.append("#" * level + " ")
        elif tag in {"ul", "ol"}:
            self._block_break()
            self._list_stack.append({"type": tag, "index": 1})
        elif tag == "li":
            self._line_break()
            indent = "  " * max(len(self._list_stack) - 1, 0)
            marker = "- "
            if self._list_stack and self._list_stack[-1]["type"] == "ol":
                index = int(self._list_stack[-1]["index"])
                marker = f"{index}. "
                self._list_stack[-1]["index"] = index + 1
            self.parts.append(indent + marker)
        elif tag in {"b", "strong"}:
            self.parts.append("**")
        elif tag in {"i", "em"}:
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "pre":
            self._block_break()
            self.parts.append("```")
            self._line_break()
        elif tag == "a":
            self.parts.append("[")
            self._link_stack.append(_normalize_href(attr_dict.get("href")))
        elif tag == "img":
            self.parts.append(_image_markdown(attr_dict))
        elif tag == "br":
            self._line_break()
        elif tag == "hr":
            self._block_break()
            self.parts.append("---")
            self._block_break()
        elif tag in {"s", "del"}:
            self.parts.append("~~")
        elif tag == "u":
            self.parts.append("<u>")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if self._skip_stack:
            if tag == self._skip_stack[-1]:
                self._skip_stack.pop()
            return

        if tag not in _KNOWN_TAGS:
            self.parts.append(f"</{tag}>")
            return

        if tag in _BLOCK_TAGS:
            self._block_break()
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._block_break()
        elif tag in {"ul", "ol"}:
            if self._list_stack:
                self._list_stack.pop()
            self._block_break()
        elif tag == "li":
            self._line_break()
        elif tag in {"b", "strong"}:
            self.parts.append("**")
        elif tag in {"i", "em"}:
            self.parts.append("*")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "pre":
            self._line_break()
            self.parts.append("```")
            self._block_break()
        elif tag == "a":
            href = self._link_stack.pop() if self._link_stack else None
            self.parts.append(f"]({href})" if href else "]")
        elif tag in {"s", "del"}:
            self.parts.append("~~")
        elif tag == "u":
            self.parts.append("</u>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        attr_dict = dict(attrs)
        if tag == "br":
            self._line_break()
        elif tag == "hr":
            self._block_break()
            self.parts.append("---")
            self._block_break()
        elif tag == "img":
            self.parts.append(_image_markdown(attr_dict))
        elif tag not in _KNOWN_TAGS:
            self.unknown_tags.add(tag)
            self.parts.append(_format_start_tag(tag, attrs, self_closing=True))

    def handle_data(self, data: str):
        if not self._skip_stack:
            self.parts.append(data)

    def handle_entityref(self, name: str):
        if not self._skip_stack:
            self.parts.append(unescape(f"&{name};"))

    def handle_charref(self, name: str):
        if not self._skip_stack:
            self.parts.append(unescape(f"&#{name};"))

    def _line_break(self):
        if self.parts and not self.output.endswith("\n"):
            self.parts.append("\n")

    def _block_break(self):
        out = self.output
        if not out:
            return
        if out.endswith("\n\n"):
            return
        if out.endswith("\n"):
            self.parts.append("\n")
        else:
            self.parts.append("\n\n")


def _format_start_tag(
    tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool = False
) -> str:
    attr_text = "".join(
        f' {name}="{escape(value, quote=True)}"' if value is not None else f" {name}"
        for name, value in attrs
    )
    suffix = "/>" if self_closing else ">"
    return f"<{tag}{attr_text}{suffix}"


def _normalize_href(href: str | None) -> str | None:
    if not href:
        return None
    href = unescape(href)
    parsed = urlparse(href)
    if parsed.netloc == "link.zhihu.com":
        target = (parse_qs(parsed.query).get("target") or [None])[0]
        if target:
            return unquote(target)
    return href


def _image_markdown(attrs: dict[str, str | None]) -> str:
    src = attrs.get("data-original") or attrs.get("src") or ""
    caption = attrs.get("data-caption") or attrs.get("alt") or "image"
    return f"![{caption}]({src})" if src else "![image]()"


def _cleanup_markdown(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
