"""
A simple hello world module.
"""

def greet(name="World"):
    """
    Greet a user by name.
    
    Args:
        name: The name to greet, defaults to "World"
        
    Returns:
        A greeting string
    """
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet()) 