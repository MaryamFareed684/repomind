import ast

code = '''
import os

def greet(name):
    return "hi " + name

class Bot:
    def run(self):
        pass
'''

tree = ast.parse(code)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        print(type(node).__name__, node.name, node.lineno, node.end_lineno)