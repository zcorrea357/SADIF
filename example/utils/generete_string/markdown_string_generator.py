# Import the MarkdownStringGenerator class from the specified module
from sadif.utils.generete_string.markdown_string_generator import MarkdownStringGenerator

# Create an instance of MarkdownStringGenerator with a specified string length of 10 characters
markdown_gen = MarkdownStringGenerator(string_length=10)

# Generate a Markdown formatted title at level 1 with the specified title
title = markdown_gen.generate_title(level=1, title="Exemplo de Título")

# Generate a Markdown formatted unordered list with 3 items
list_content = markdown_gen.generate_list(num_items=3, ordered=False)

# Generate a Markdown formatted code block with 5 lines in Python
code_block = markdown_gen.generate_code_block(num_lines=5, language="python")

# Generate a Markdown formatted paragraph with 20 words
paragraph = markdown_gen.generate_paragraph(num_words=20)

# Generate a complete Markdown document combining title, list, code block, and paragraph
markdown_document = markdown_gen.generate_markdown_document(
    title="Exemplo de Documento Markdown",
    list_items=3,
    code_lines=5,
    paragraph_words=20,
    language="python",
)

# Print the generated individual elements and the full document to check the output
print(title, list_content, code_block, paragraph, markdown_document)
