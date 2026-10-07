from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_markdown import (
    MarkdownConverter,
)


class TemplateRenderer:
    """
    Renderiza um template de comentário (lista de blocos {"type", "value"}, como os de
    CaseCommentTemplate) em Markdown, preenchendo os placeholders "{nome}" com os kwargs.

    Um placeholder sem valor em kwargs levanta KeyError com o nome do placeholder.
    """

    def __init__(self, template, **kwargs):
        self.template = template
        self.kwargs = kwargs
        self._converter = MarkdownConverter()

    def _fill(self, text):
        return text.format(**self.kwargs) if isinstance(text, str) else text

    def _fill_any(self, value):
        if isinstance(value, str):
            return self._fill(value)
        if isinstance(value, list):
            return [self._fill_any(item) for item in value]
        if isinstance(value, dict):
            return {key: self._fill_any(item) for key, item in value.items()}
        return value

    def render_header(self, value):
        level = value.get("level", 1)
        text = self._fill(value.get("text", ""))
        return "#" * level + " " + text

    def render_paragraph(self, value):
        return self._fill(value)

    def render_unordered_list(self, values):
        return "\n".join(["- " + self._fill(value) for value in values])

    def render(self):
        rendered_template = []
        for item in self.template:
            item_type = item.get("type")
            item_value = item.get("value")
            if item_type == "header":
                rendered_template.append(self.render_header(item_value))
            elif item_type == "paragraph":
                rendered_template.append(self.render_paragraph(item_value))
            elif item_type == "unordered_list":
                rendered_template.append(self.render_unordered_list(item_value))
            else:
                # Demais tipos suportados pelo MarkdownConverter (ordered_list, table, link,
                # image, fenced_code_block); tipos desconhecidos são ignorados.
                converted = self._converter.convert(
                    [{"type": item_type, "value": self._fill_any(item_value)}]
                )
                if converted:
                    rendered_template.append(converted)
        return "\n\n".join(rendered_template)
