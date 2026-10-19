"""Offset-preserving Lua tokenizer. CC0-1.0."""
import re
from dataclasses import dataclass


@dataclass
class Token:
    kind: str
    text: str
    start: int
    end: int
    line: int


LONG = re.compile(r'\[(=*)\[')
NUMBER = re.compile(r'(?:0[xX][0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?\d+)?|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)')
IDENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')


def tokenize(source):
    tokens, warnings = [], []
    i, line = 0, 1
    while i < len(source):
        start, first_line = i, line
        c = source[i]
        if c.isspace():
            line += c == '\n'
            i += 1
            continue
        comment = source.startswith('--', i)
        offset = i + 2 if comment else i
        long = LONG.match(source, offset)
        if long:
            close = ']' + long[1] + ']'
            end = source.find(close, long.end())
            i = len(source) if end < 0 else end + len(close)
            if end < 0:
                warnings.append((first_line, 'lexical', 'Unterminated long string or comment'))
            kind = 'invalid' if end < 0 else 'string'
        elif comment:
            end = source.find('\n', i)
            i = len(source) if end < 0 else end
            kind = 'comment'
        elif c in "\"'":
            i += 1
            kind = 'string'
            while i < len(source):
                if source[i] == '\\':
                    i += 3 if source.startswith('\\\r\n', i) else 2
                elif source[i] == c:
                    i += 1
                    break
                elif source[i] in '\r\n':
                    warnings.append((first_line, 'lexical', 'Unescaped newline in quoted string'))
                    kind = 'invalid'
                    break
                else:
                    i += 1
            else:
                warnings.append((first_line, 'lexical', 'Unterminated quoted string'))
                kind = 'invalid'
            i = min(i, len(source))
        else:
            match = NUMBER.match(source, i) or IDENT.match(source, i)
            if match:
                i = match.end()
                kind = 'number' if NUMBER.fullmatch(match[0]) else 'id'
            else:
                pair = source[i:i+2]
                i += 3 if source.startswith('...', i) else (2 if pair in ('==', '~=', '<=', '>=', '..', '//') else 1)
                kind = 'punct'
        raw = source[start:i]
        line += raw.count('\n')
        if not comment:
            tokens.append(Token(kind, raw, start, i, first_line))
    tokens.append(Token('eof', '', len(source), len(source), line))
    return tokens, warnings


def string_value(raw):
    long = LONG.match(raw)
    if long:
        value = raw[long.end():-(len(long[1])+2)]
        return re.sub(r'^\r?\n', '', value, count=1)
    body = raw[1:-1]
    escapes = {'a': '\a', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r',
               't': '\t', 'v': '\v', '\n': '\n', '\\': '\\', '"': '"', "'": "'"}
    def replace(m):
        s = m[1]
        if s.isdigit():
            return chr(int(s) % 256)
        if s.startswith('x') and len(s) == 3:
            return chr(int(s[1:], 16))
        if s.startswith('z'):
            return ''
        return escapes.get(s, s)
    return re.sub(r'\\(\d{1,3}|x[0-9a-fA-F]{2}|z\s*|\r?\n|.)', replace, body)
