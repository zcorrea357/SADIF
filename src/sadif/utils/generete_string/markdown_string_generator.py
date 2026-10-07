import random
import string


class MarkdownStringGenerator:
    """
    A class for generating Markdown-formatted strings. It supports generating random
    Markdown elements such as titles, lists, code blocks, and paragraphs with specified
    or random content.

    Attributes
    ----------
    string_length : int
        The default length for generated random strings.

    Methods
    -------
    __init__(self, string_length: int = 10)
        Initializes the class with a default length for random strings.
    _random_string(self, length: int) -> str
        Generates a random alphanumeric string of specified length.
    generate_title(self, level: int, title: Optional[str] = None) -> str
        Generates a Markdown formatted title of a given level. Generates a random title if none is provided.
    generate_list(self, num_items: int, ordered: bool = False) -> str
        Generates a Markdown formatted list, either ordered or unordered, with specified number of items.
    generate_code_block(self, num_lines: int, language: str = "") -> str
        Generates a Markdown formatted code block with specified number of lines and optional language annotation.
    generate_paragraph(self, num_words: int) -> str
        Generates a Markdown formatted paragraph with a specified number of words.
    generate_markdown_document(self, title: str, list_items: int, code_lines: int, paragraph_words: int, language: str = "python") -> str
        Generates a full Markdown document containing a title, a list, a code block, and a paragraph.
    """

    def __init__(self, string_length: int = 10) -> None:
        """
        Initializes the MarkdownStringGenerator instance with a default length for the
        random strings used in generating Markdown elements.

        Parameters
        ----------
        string_length : int
            The default length for generated random strings. Defaults to 10.
        """
        if not isinstance(string_length, int) or string_length < 1:
            error_message = "O tamanho da string deve ser um inteiro positivo."
            raise ValueError(error_message)
        self.string_length = string_length

    def _random_string(self, length: int) -> str:
        """
        Generates a random alphanumeric string of the specified length.

        Parameters
        ----------
        length : int
            The length of the random string to generate.

        Returns
        -------
        str
            A random alphanumeric string of the specified length.
        """
        return "".join(random.choices(string.ascii_letters + string.digits, k=length))

    def generate_title(self, level: int, title: str | None = None) -> str:
        """
        Generates a Markdown formatted title at the specified level. If no title is
        provided, generates a random title.

        Parameters
        ----------
        level : int
            The level of the title (1-6 corresponding to h1-h6 in Markdown).
        title : Optional[str]
            An optional title string. If None, a random title is generated.

        Returns
        -------
        str
            A Markdown formatted title string.

        Raises
        ------
        ValueError
            If the level is not between 1 and 6.
        """
        if not 1 <= level <= 6:
            error_message = "Nível do título deve estar entre 1 e 6."
            raise ValueError(error_message)
        title = title or self._random_string(self.string_length)
        return f"{'#' * level} {title}"

    def generate_list(self, num_items: int, ordered: bool = False) -> str:
        """
        Generates a Markdown formatted list, either ordered or unordered, with the
        specified number of items.

        Parameters
        ----------
        num_items : int
            The number of items in the list.
        ordered : bool
            True to generate an ordered list, False for unordered.

        Returns
        -------
        str
            A Markdown formatted list as a string.

        Raises
        ------
        ValueError
            If the number of items is not a positive integer.
        """
        if not isinstance(num_items, int) or num_items < 1:
            error_message = "O número de itens deve ser um inteiro positivo."
            raise ValueError(error_message)
        prefix = "1." if ordered else "-"
        items = [f"{prefix} {self._random_string(self.string_length)}" for _ in range(num_items)]
        return "\n".join(items)

    def generate_code_block(self, num_lines: int, language: str = "") -> str:
        """
        Generates a Markdown formatted code block with the specified number of lines
        and an optional language annotation.

        Parameters
        ----------
        num_lines : int
            The number of lines in the code block.
        language : str
            An optional language annotation for the code block.

        Returns
        -------
        str
            A Markdown formatted code block as a string.

        Raises
        ------
        ValueError
            If the number of lines is not a positive integer.
        """
        if not isinstance(num_lines, int) or num_lines < 1:
            error_message = "O número de linhas deve ser um inteiro positivo."
            raise ValueError(error_message)
        lines = [self._random_string(random.randint(10, 20)) for _ in range(num_lines)]
        return f"```{language}\n" + "\n".join(lines) + "\n```"

    def generate_paragraph(self, num_words: int) -> str:
        """
        Generates a Markdown formatted paragraph with the specified number of words.

        Parameters
        ----------
        num_words : int
            The number of words in the paragraph.

        Returns
        -------
        str
            A Markdown formatted paragraph as a string.

        Raises
        ------
        ValueError
            If the number of words is not a positive integer.
        """
        if not isinstance(num_words, int) or num_words < 1:
            msg = "Number of words must be a positive integer."
            raise ValueError(msg)
        words = [self._random_string(random.randint(5, 10)) for _ in range(num_words)]
        return " ".join(words)

    def generate_markdown_document(
        self,
        title: str,
        list_items: int,
        code_lines: int,
        paragraph_words: int,
        language: str = "python",
    ) -> str:
        """
        Generates a full Markdown document containing a title, a list, a code block,
        and a paragraph.

        Parameters
        ----------
        title : str
            The title of the document.
        list_items : int
            The number of items in the list.
        code_lines : int
            The number of lines in the code block.
        paragraph_words : int
            The number of words in the paragraph.
        language : str
            The programming language annotation for the code block. Defaults to "python".

        Returns
        -------
        str
            A complete Markdown document as a string.
        """
        document = self.generate_title(2, title) + "\n\n"
        document += self.generate_list(list_items) + "\n\n"
        document += self.generate_code_block(code_lines, language) + "\n\n"
        document += self.generate_paragraph(paragraph_words)
        return document
