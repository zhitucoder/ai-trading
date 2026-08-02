#!/bin/bash
INPUT_DIR="/home/rick/workspace/ai-trading/analysis/行业分析_公众号/md"
HTML_DIR="/home/rick/workspace/ai-trading/analysis/行业分析_公众号/html"
WCTOOL="/home/rick/.claude/skills/wechat-article-typeset/wechat-copy.js"
LINK_FILE="/home/rick/workspace/ai-trading/analysis/行业分析_公众号/all_links.txt"

mkdir -p "$HTML_DIR"

echo "=== 📱 行业分析 公众号发布链接 ===" > "$LINK_FILE"
echo "生成日期: 2026-07-30" >> "$LINK_FILE"
echo "" >> "$LINK_FILE"

count=0
for f in "$INPUT_DIR"/*.md; do
    [ -f "$f" ] || continue
    base=$(basename "$f" .md)
    count=$((count+1))
    echo "[$count/47] $base"

    TMP_MD="/tmp/wechat_$base.md"
    cp "$f" "$TMP_MD"

    cd "$INPUT_DIR"
    result=$(node "$WCTOOL" --preset "墨色书香" "$TMP_MD" 2>&1)
    url=$(echo "$result" | grep -oP 'https?://[^\s"<>]+' | head -1)

    if [ -n "$url" ]; then
        mkdir -p "$HTML_DIR/$base"
        echo "- [$base]($url)" >> "$LINK_FILE"
        echo "  Link OK"

        if [ -f "$INPUT_DIR/article.preset.html" ]; then
            mv "$INPUT_DIR/article.preset.html" "$HTML_DIR/$base/index.html"
        fi
        if [ -f "$INPUT_DIR/wechat-preview-url.txt" ]; then
            mv "$INPUT_DIR/wechat-preview-url.txt" "$HTML_DIR/$base/"
        fi
    else
        echo "- $base (失败)" >> "$LINK_FILE"
        echo "  ERROR: $result"
    fi

    rm -f "$TMP_MD"
done

echo "" >> "$LINK_FILE"
echo "共 $count 篇" >> "$LINK_FILE"

echo ""
echo "=== 预览链接 ==="
cat "$LINK_FILE"
