# pip install jieba
import jieba
import jieba.analyse


class ChineseSegmenter:
    """
    # IMPORTANT: Add your company-specific terms
    # Without this, product names and internal terms get split incorrectly
    """

    def __init__(self, custom_dict_path: str | None = None):
        if custom_dict_path:
            # Load YOUR specific terms
            # e.g. product names, internal jargon
            jieba.load_userdict(custom_dict_path)

        jieba.initialize()

    def segment(self, text: str) -> str:
        """Add spaces between Chinese words for downstream processing"""
        words = jieba.cut(text, cut_all=False)  # Precise mode
        return " ".join(words)

    def extract_keywords(self, text: str, top_k: int = 10) -> list:
        """Extract most important keywords (great for metadata tagging)"""
        return jieba.analyse.extract_tags(text, topK=top_k)

    def segment_for_search(self, text: str) -> str:
        """Search mode — finds more possible words, better for queries"""
        words = jieba.cut_for_search(text)
        return " ".join(words)
