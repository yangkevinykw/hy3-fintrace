"""Recognize explicit single-operation descriptions; abstain on other prose.

Full sentence patterns deliberately exclude negations, quotations, multi-step
plans and implicit financial formulas. This checks internal consistency only.
"""
import re

PATTERNS = {
    'add': [r'(?:将|把)?(?:所列)?(?:两项|两个)(?:数值|操作数|输入值)(?:相加|求和)',
            r'(?:计算|求)(?:所列)?(?:两项|两个)(?:数值|操作数|输入值)的和',
            r'(?:compute|calculate|take) the sum of (?:the )?(?:two|both) (?:operands|inputs|values)'],
    'subtract': [r'(?:计算|求)(?:所列)?(?:两项|两个)(?:数值|操作数|输入值)的差',
                 r'(?:用)?第一(?:项|个操作数|个输入值)减去第二(?:项|个操作数|个输入值)',
                 r'subtract the second (?:operand|input|value) from the first'],
    'multiply': [r'(?:计算|求)(?:所列)?(?:两项|两个)(?:数值|操作数|输入值)的(?:乘积|积)',
                 r'(?:将|把)?(?:所列)?(?:两项|两个)(?:数值|操作数|输入值)相乘',
                 r'(?:compute|calculate|take) the product of (?:the )?(?:two|both) (?:operands|inputs|values)',
                 r'multiply (?:the )?(?:two|both) (?:operands|inputs|values)'],
    'divide': [r'用第一(?:项|个操作数|个输入值)除以第二(?:项|个操作数|个输入值)(?:，求得对应比值)?',
               r'(?:计算|求)第一(?:项|个操作数)与第二(?:项|个操作数)的商',
               r'divide the first (?:operand|input|value) by the second'],
}


def explicit_operation(text):
    if not isinstance(text, str) or len(text) > 300:
        return None
    value = text.strip().rstrip('。.!！').strip().lower()
    matches = [op for op, patterns in PATTERNS.items()
               if any(re.fullmatch(pattern, value) for pattern in patterns)]
    return matches[0] if len(matches) == 1 else None
