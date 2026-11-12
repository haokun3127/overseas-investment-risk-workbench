"""Conservative same-currency amount checks; no exchange rates or inferred facts."""
import re
from decimal import Decimal, InvalidOperation


NUMBER = r'\d+(?:[.,]\d+)*'
SCALE = r'triliun|miliar|milyar|juta|ribu|trillion|billion|million|thousand|万亿|千亿|百亿|十亿|亿|千万|百万|十万|万|千|百'
CURRENCY = r'印尼盾|印度尼西亚盾|印度尼西亚卢比|印尼卢比|rupiahs?|IDR|美元|美金|US\$|USD|人民币|RMB|CNY'
PREFIX = re.compile(rf'(?<![A-Za-z])(?P<currency>Rp\.?|IDR|USD|US\$|RMB|CNY)\s*(?P<number>{NUMBER})\s*(?P<scale>{SCALE})?', re.I)
SUFFIX = re.compile(rf'(?P<number>{NUMBER})\s*(?P<scale>{SCALE})?\s*(?P<currency>{CURRENCY})(?![A-Za-z])', re.I)
MULTIPLIERS = {
    'triliun': 10**12, 'miliar': 10**9, 'milyar': 10**9, 'juta': 10**6, 'ribu': 10**3,
    'trillion': 10**12, 'billion': 10**9, 'million': 10**6, 'thousand': 10**3,
    '万亿': 10**12, '千亿': 10**11, '百亿': 10**10, '十亿': 10**9, '亿': 10**8,
    '千万': 10**7, '百万': 10**6, '十万': 10**5, '万': 10**4, '千': 10**3, '百': 10**2,
}


class AmountMismatch(ValueError):
    pass


def _currency(value):
    value = value.casefold().rstrip('.')
    if value in ('usd', 'us$', '美元', '美金'):
        return 'USD'
    if value in ('rmb', 'cny', '人民币'):
        return 'CNY'
    return 'IDR'


def amounts(text):
    # Chinese amounts often write the currency unit twice: “100万元人民币”.
    # Normalize only explicitly named CNY, never infer the currency of a bare “元”.
    text = re.sub(rf'({NUMBER})\s*({SCALE})?元人民币', r'\1\2人民币', text, flags=re.I)
    text = re.sub(rf'人民币\s*({NUMBER})\s*({SCALE})?元', r'\1\2人民币', text, flags=re.I)
    result = []
    for pattern in (PREFIX, SUFFIX):
        for match in pattern.finditer(text):
            number, scale = match['number'], (match['scale'] or '').casefold()
            # Indonesian uses a decimal comma and grouping dots. English/Chinese use the reverse.
            indonesian = scale in ('triliun', 'miliar', 'milyar', 'juta', 'ribu') or match['currency'].casefold().startswith(('rp', 'rupiah'))
            if indonesian:
                if re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:,\d+)?', number):
                    number = number.replace('.', '').replace(',', '.')
                elif ',' in number:
                    number = number.replace('.', '').replace(',', '.')
            else:
                number = number.replace(',', '')
            try:
                value = Decimal(number) * MULTIPLIERS.get(scale, 1)
            except InvalidOperation:
                continue
            result.append((_currency(match['currency']), value, match.group()))
    return result


def verify_amounts(answer, evidence):
    """Require explicit amounts in a factual answer to occur in its cited evidence.

    Only explicit supported currency expressions are checked. This does not claim to
    validate every number, unnamed monetary amounts, dates, or semantic relationships.
    """
    allowed = {(currency, value) for currency, value, _ in amounts(evidence)}
    for currency, value, original in amounts(answer):
        if (currency, value) not in allowed:
            raise AmountMismatch(f'金额与引用原文不一致：{original}。请保留原文币种和数量单位，不推算汇率或补造金额。')
