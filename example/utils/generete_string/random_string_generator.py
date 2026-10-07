# Import the RandomStringGenerator class from the specified module
from sadif.utils.generete_string.random_string_generator import RandomStringGenerator

# Create an instance of RandomStringGenerator with a specified length of 10 characters
random_string_gen = RandomStringGenerator(string_length=10)

# Generate a random string formatted as a title using a provided base string "Python"
formatted_title = random_string_gen.generate_string_title("Python")

# Generate a random string formatted as a paragraph containing 10 words
formatted_paragraph = random_string_gen.generate_string_paragraph(10)

# Print the generated title and paragraph to check the output
print(formatted_title, formatted_paragraph)
