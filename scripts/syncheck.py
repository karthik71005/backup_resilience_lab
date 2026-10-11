import ast
import sys
for p in sys.argv[1:]:
    ast.parse(open(p).read())
    print("syntax ok:", p)
