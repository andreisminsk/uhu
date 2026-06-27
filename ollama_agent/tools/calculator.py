"""Calculator tool — safely evaluate mathematical expressions."""

import ast
import math
import operator


# Safe operators mapping
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Safe math constants and functions
_SAFE_NAMES = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "nan": math.nan,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "cbrt": math.cbrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "ln": math.log,
    "exp": math.exp,
    "pow": math.pow,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "degrees": math.degrees,
    "radians": math.radians,
    "hypot": math.hypot,
    "dist": math.dist,
}


def _safe_eval(expr):
    """Safely evaluate a mathematical expression using AST."""
    tree = ast.parse(expr, mode="eval")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, complex)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")
        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in _SAFE_OPS:
                raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
            return _SAFE_OPS[type(node.op)](_eval(node.operand))
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in _SAFE_OPS:
                raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
            return _SAFE_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        elif isinstance(node, ast.Call):
            func = _eval(node.func) if isinstance(node.func, ast.Name) else None
            if func is None or func not in _SAFE_NAMES.values():
                raise ValueError(f"Unsupported function call")
            args = [_eval(a) for a in node.args]
            return func(*args)
        elif isinstance(node, ast.Name):
            if node.id in _SAFE_NAMES:
                val = _SAFE_NAMES[node.id]
                if callable(val):
                    return val  # function reference
                return val
            raise ValueError(f"Unsupported name: {node.id}")
        elif isinstance(node, ast.Tuple):
            return tuple(_eval(e) for e in node.elts)
        elif isinstance(node, ast.List):
            return [_eval(e) for e in node.elts]
        else:
            raise ValueError(f"Unsupported expression: {type(node).__name__}")

    return _eval(tree)


class CalculatorTool:
    name = "calculator"
    description = "Evaluate mathematical expressions safely"
    system_prompt = """## calculator

Evaluates mathematical expressions safely. ALWAYS use this tool for ANY mathematical computation — never attempt mental arithmetic, even for simple calculations. LLMs are unreliable at math; this tool guarantees correct results. If a user asks you to compute, calculate, solve, or evaluate any numeric expression, invoke this tool rather than computing yourself.

Parameters (JSON object):
- expression (string, required): The mathematical expression to evaluate. Supports:
  - Basic arithmetic: +, -, *, /, //, %, **
  - Math functions: sqrt, cbrt, sin, cos, tan, asin, acos, atan, atan2, sinh, cosh, tanh, log, log2, log10, ln, exp, pow, ceil, floor, factorial, gcd, abs, round, min, max, degrees, radians, hypot, dist
  - Constants: pi, e, tau, inf
  - Parentheses for grouping
- precision (integer, optional): Round result to this many decimal places. Omit for full precision.

Examples:
- {"expression": "2**10"} → 1024
- {"expression": "sqrt(2) * sin(pi/4)"} → 1.0
- {"expression": "log(e**5)"} → 5.0
- {"expression": "factorial(20)"} → 2432902008176640000
- {"expression": "hypot(3, 4)"} → 5.0"""

    def execute(self, params, workdir=None):
        expr = params.get("expression", "").strip()
        if not expr:
            return {"error": "Parameter 'expression' is required."}

        precision = params.get("precision")

        try:
            result = _safe_eval(expr)
        except Exception as exc:
            return {"error": f"Failed to evaluate: {exc}", "expression": expr}

        # Round if precision specified
        if precision is not None and isinstance(result, (int, float)):
            result = round(result, int(precision))

        # Format result nicely
        if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
            result = int(result)

        return {
            "expression": expr,
            "result": result,
            "formatted": f"{expr} = {result}"
        }
