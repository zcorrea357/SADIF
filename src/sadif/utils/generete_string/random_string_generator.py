import random
import string


class RandomStringGenerator:
    """
    A class for generating formatted random strings. It can generate strings
    formatted with a given word or generate a paragraph with a specified number
    of random words.

    Attributes
    ----------
    string_length : int
        The default length for generated random strings.

    Methods
    -------
    __init__(self, string_length: int = 10)
        Initializes the class with a default length for random strings.
    generate_string_title(self, word: str) -> str
        Generates a random string formatted with the provided word.
    generate_string_paragraph(self, num_words: int) -> str
        Generates a paragraph composed of a specified number of random words.
    """

    def __init__(self, string_length: int = 10) -> None:
        """
        Initializes the RandomStringGenerator instance with a default length for the
        random strings used in generating formatted strings.

        Parameters
        ----------
        string_length : int
            The default length for generated random strings.
        """
        if not isinstance(string_length, int) or string_length < 1:
            error_message = "O tamanho da string deve ser um inteiro positivo."
            raise ValueError(error_message)
        self.string_length = string_length

    def generate_string_title(self, word: str) -> str:
        """
        Generates a random string formatted with the provided word. The format
        follows the pattern: "test de {word} - {random_string}".

        Parameters
        ----------
        word : str
            The word to be included in the generated string.

        Returns
        -------
        str
            A formatted string including the provided word and a random string.

        Raises
        ------
        TypeError
            If the input word is not a string.
        """
        if not isinstance(word, str):
            msg = "The word must be a string."
            raise TypeError(msg)
        random_string = "".join(
            random.choices(string.ascii_letters + string.digits, k=self.string_length)
        )
        return f"test de {word} - {random_string}"

    def generate_string_paragraph(self, num_words: int) -> str:
        """
        Generates a paragraph composed of a specified number of random words. Each word
        is randomly generated with a length between 5 and 10 characters.

        Parameters
        ----------
        num_words : int
            The number of random words to include in the paragraph.

        Returns
        -------
        str
            A paragraph composed of the specified number of random words.

        Raises
        ------
        ValueError
            If the number of words is not a positive integer.
        """
        if not isinstance(num_words, int) or num_words < 1:
            error_message = "O número de palavras deve ser um inteiro positivo."
            raise ValueError(error_message)  # Mensagem armazenada em uma variável
        paragraph = []
        for _ in range(num_words):
            word_length = random.randint(5, 10)
            word = "".join(random.choices(string.ascii_letters, k=word_length))
            paragraph.append(word)
        return " ".join(paragraph)
