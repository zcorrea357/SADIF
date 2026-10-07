class MarkdownConverter:
    def __init__(self, unordered_list_char="-"):
        self.unordered_list_char = unordered_list_char

    def convert_header(self, value):
        level = value.get("level", 1)
        text = value.get("text", "")
        return f"{'#' * level} {text}"

    def convert_unordered_list(self, value):
        return "\n".join([f"{self.unordered_list_char} {item}" for item in value])

    def convert_ordered_list(self, value):
        return "\n".join([f"{i}. {item}" for i, item in enumerate(value, start=1)])

    def convert_fenced_code_block(self, value):
        return f"```\n{value}\n```"

    def convert_link(self, value):
        return f"[{value.get('text', '')}]({value.get('url', '')})"

    def convert_image(self, value):
        return f"![{value.get('alt_text', '')}]({value.get('url', '')})"

    def convert_paragraph(self, value):
        return str(value)

    def convert_table(self, value):
        headers = [str(header) for header in value.get("headers", [])]
        table_str = "| " + " | ".join(headers) + " |"
        table_str += "\n| " + " | ".join(["---"] * len(headers)) + " |"
        for row in value.get("rows", []):
            # células numéricas/None não quebram o join
            table_str += f"\n| {' | '.join(str(cell) for cell in row)} |"
        return table_str

    def convert(self, content_list):
        conversion_methods = {
            "header": self.convert_header,
            "paragraph": self.convert_paragraph,
            "unordered_list": self.convert_unordered_list,
            "ordered_list": self.convert_ordered_list,
            "fenced_code_block": self.convert_fenced_code_block,
            "link": self.convert_link,
            "image": self.convert_image,
            "table": self.convert_table,
        }

        markdown_list = []
        for item in content_list:
            key = item.get("type")
            value = item.get("value")

            if not value or key not in conversion_methods:
                continue

            markdown_list.append(conversion_methods[key](value))

        return "\n".join(markdown_list)
