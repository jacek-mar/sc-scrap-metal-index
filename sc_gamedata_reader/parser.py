"""Conservative static Lua assignment parser. CC0-1.0."""
import math
from pathlib import Path
from .lexer import tokenize, string_value
from .contract import FORMAT_VERSION, CALL_FORMAT_VERSION, ParseResult

KEYWORDS = frozenset(('and', 'break', 'do', 'else', 'elseif', 'end', 'false',
                      'for', 'function', 'goto', 'if', 'in', 'local', 'nil',
                      'not', 'or', 'repeat', 'return', 'then', 'true', 'until', 'while'))


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, source, label):
        self.source, self.label = source, label
        self.tokens, lexical = tokenize(source)
        self.i = 0
        self.warnings = []
        self.assignments = []
        self.functions = []
        self.calls = []
        self.active_scope = None
        self.active_conditional = False
        for line, code, message in lexical:
            self.warn(line, code, message)

    @property
    def t(self):
        return self.tokens[self.i]

    def warn(self, line, code, message):
        self.warnings.append(dict(file=self.label, line=line, code=code, message=message))

    def take(self, text=None):
        token = self.t
        if text is not None and token.text != text:
            raise ParseError('Expected ' + text)
        if token.kind == 'eof':
            raise ParseError('Unexpected end of file')
        self.i += 1
        return token

    def slice(self, start):
        return self.source[self.tokens[start].start:self.tokens[self.i-1].end]

    def record_call(self, start, callee, arguments):
        first, last = self.tokens[start], self.tokens[self.i-1]
        self.calls.append(dict(callee=callee.get('$ref'), callee_value=callee,
                               arguments=arguments, source=self.slice(start),
                               start=first.start, end=last.end, line=first.line,
                               end_line=last.line + last.text.count('\n'),
                               scope=self.active_scope,
                               conditional=self.active_conditional, context='value'))

    def expression(self, minimum=0, depth=0):
        if depth > 100:
            raise ParseError('Nesting limit exceeded')
        start = self.i
        token = self.take()
        if token.text in ('-', '+', '#', 'not'):
            value = self.expression(7, depth+1)
            if type(value) in (int, float) and token.text in ('-', '+'):
                value = -value if token.text == '-' else value
            else:
                value = {'$expr': self.slice(start)}
        elif token.text == 'function':
            # Keep surrounding data even when a table contains executable code.
            # Balanced skipping records its source, never its body assignments.
            self.skip(start)
            if self.tokens[self.i-1].text != 'end':
                raise ParseError('Unterminated function value')
            value = {'$expr': self.slice(start)}
            self.warn(token.line, 'opaque_function', 'Function value preserved without execution')
        elif token.text == '{':
            entries, implicit, sequence = [], 1, True
            while self.t.text != '}':
                if self.t.text == '[':
                    self.take('[')
                    key = self.expression(depth=depth+1)
                    self.take(']'); self.take('=')
                    sequence = False
                elif self.t.kind == 'id' and self.tokens[self.i+1].text == '=':
                    key = self.take().text
                    self.take('=')
                    sequence = False
                else:
                    key = implicit
                    implicit += 1
                item = self.expression(depth=depth+1)
                entries.append({'key': key, 'value': item})
                if self.t.text not in (',', ';'):
                    break
                self.take()
            self.take('}')
            if entries and sequence:
                value = [e['value'] for e in entries]
            elif entries and all(type(e['key']) is str for e in entries) and len({e['key'] for e in entries}) == len(entries) and not any(e['key'].startswith('$') for e in entries):
                value = {e['key']: e['value'] for e in entries}
            else:
                value = {'$table': entries}
        elif token.text == '(':
            value = self.expression(depth=depth+1)
            self.take(')')
        elif token.kind == 'number':
            raw = token.text
            value = (float.fromhex(raw) if any(c in raw.lower() for c in '.p') else int(raw, 16)) if raw.lower().startswith('0x') else (float(raw) if any(c in raw.lower() for c in '.e') else int(raw))
        elif token.kind == 'string':
            value = string_value(token.text)
        elif token.text == '...':
            value = {'$expr': '...'}
        elif token.text in ('true', 'false', 'nil'):
            value = {'true': True, 'false': False, 'nil': None}[token.text]
        elif token.kind == 'id' and token.text not in KEYWORDS:
            value = {'$ref': token.text}
        else:
            raise ParseError('Unsupported value')
        while self.t.text in ('.', '[', ':', '(', '{') or self.t.kind == 'string':
            # A constructor following a literal table is a new statement/error.
            if not isinstance(value, dict) or not any(k in value for k in ('$ref', '$call', '$expr')):
                break
            suffix = self.take().text
            if suffix in ('.', ':'):
                if self.t.kind != 'id':
                    raise ParseError('Expected field name')
                self.take()
                value = {('$ref' if '$ref' in value else '$expr'): self.slice(start)}
            elif suffix == '[':
                self.expression(depth=depth+1); self.take(']')
                value = {('$ref' if '$ref' in value else '$expr'): self.slice(start)}
            elif suffix == '(':
                callee, arguments = value, []
                while self.t.text != ')':
                    arguments.append(self.expression(depth=depth+1))
                    if self.t.text != ',':
                        break
                    self.take(',')
                self.take(')')
                self.record_call(start, callee, arguments)
                value = {'$call': self.slice(start)}
            else:
                self.i -= 1
                callee = value
                argument = self.expression(9, depth+1)
                self.record_call(start, callee, [argument])
                value = {'$call': self.slice(start)}
        precedence = {'or': 1, 'and': 2, '==': 3, '~=': 3, '<': 3, '>': 3, '<=': 3, '>=': 3, '..': 4, '+': 5, '-': 5, '*': 6, '/': 6, '//': 6, '%': 6, '^': 8}
        while self.t.text in precedence and precedence[self.t.text] >= minimum:
            op = self.take().text
            right = self.expression(precedence[op] + (0 if op in ('^', '..') else 1), depth+1)
            if type(value) in (int, float) and type(right) in (int, float) and op in ('+', '-', '*', '/', '//', '%', '^'):
                try:
                    if op == '^' and (abs(right) > 1024 or abs(value) > 1e100):
                        raise ValueError()
                    if op == '+': value = value + right
                    elif op == '-': value = value - right
                    elif op == '*': value = value * right
                    elif op == '/': value = value / right
                    elif op == '//': value = value // right
                    elif op == '%': value = value % right
                    else: value = value ** right
                    if isinstance(value, complex) or not math.isfinite(value):
                        raise ValueError()
                except (ArithmeticError, ValueError):
                    self.warn(token.line, 'arithmetic', 'Unsafe or nonfinite arithmetic preserved')
                    value = {'$expr': self.slice(start)}
            else:
                value = {'$expr': self.slice(start)}
        if type(value) is float and not math.isfinite(value):
            self.warn(token.line, 'arithmetic', 'Nonfinite number preserved')
            value = {'$expr': self.slice(start)}
        return value

    def target(self):
        if self.t.kind != 'id' or self.t.text in KEYWORDS:
            raise ParseError('Expected assignment')
        result = self.take().text
        while self.t.text in ('.', '['):
            if self.take().text == '.':
                if self.t.kind != 'id':
                    raise ParseError('Expected target field')
                result += '.' + self.take().text
            else:
                start = self.i
                self.expression()
                result += '[' + ''.join(t.text for t in self.tokens[start:self.i]) + ']'
                self.take(']')
        return result

    def skip(self, start, stops=()):
        self.i = start
        blocks, brackets = [], []
        waiting_do = 0
        while self.t.kind != 'eof':
            token = self.t
            s = token.text
            if self.i > start and not blocks and s in stops:
                # A damaged constructor must not consume its enclosing block.
                return
            if self.i > start and not blocks and not brackets:
                previous = self.tokens[self.i-1].text
                if (token.line > self.tokens[self.i-1].line and previous not in ('=', ',', 'local')) or previous == ';':
                    return
            self.i += 1
            if token.kind in ('string', 'number'):
                continue
            if s in ('(', '{', '['): brackets.append(s)
            elif s in (')', '}', ']') and brackets: brackets.pop()
            elif s in ('function', 'if', 'for', 'while', 'repeat'):
                blocks.append(s)
                if s in ('for', 'while'): waiting_do += 1
            elif s == 'do':
                if waiting_do: waiting_do -= 1
                else: blocks.append(s)
            elif s in ('end', 'until') and blocks:
                blocks.pop()
                if not blocks and not brackets and s == 'end':
                    return

    def header(self, terminator):
        """Consume a block header without evaluating its condition."""
        brackets = []
        while self.t.kind != 'eof':
            token = self.t
            if not brackets and token.text == terminator:
                self.take()
                return
            self.take()
            if token.kind == 'string':
                continue
            if token.text in ('(', '[', '{'):
                brackets.append(token.text)
            elif token.text in (')', ']', '}') and brackets:
                brackets.pop()
        raise ParseError('Unterminated block header')

    def statements(self, scope=None, conditional=False, stops=(), depth=0):
        if depth > 100:
            raise ParseError('Block nesting limit exceeded')
        while self.t.kind != 'eof' and self.t.text not in stops:
            if self.t.text == ';':
                self.take(); continue
            start, line = self.i, self.t.line
            self.active_scope, self.active_conditional = scope, conditional
            call_checkpoint = len(self.calls)
            try:
                keyword = self.t.text
                if keyword == 'function':
                    if scope is not None:
                        raise ParseError('Nested function skipped')
                    self.take('function')
                    name = self.take()
                    if name.kind != 'id':
                        raise ParseError('Expected function name')
                    name = name.text
                    while self.t.text in ('.', ':'):
                        name += self.take().text
                        part = self.take()
                        if part.kind != 'id':
                            raise ParseError('Expected function name')
                        name += part.text
                    self.take('(')
                    self.header(')')
                    function = dict(name=name, line=line, end_line=None)
                    self.functions.append(function)
                    self.statements(name, conditional, ('end',), depth+1)
                    function['end_line'] = self.take('end').line
                    continue
                if keyword == 'if':
                    self.take('if')
                    self.header('then')
                    self.statements(scope, True, ('elseif', 'else', 'end'), depth+1)
                    while self.t.text == 'elseif':
                        self.take('elseif')
                        self.header('then')
                        self.statements(scope, True, ('elseif', 'else', 'end'), depth+1)
                    if self.t.text == 'else':
                        self.take('else')
                        self.statements(scope, True, ('end',), depth+1)
                    self.take('end')
                    continue
                if keyword in ('for', 'while', 'do', 'repeat'):
                    self.take()
                    if keyword in ('for', 'while'):
                        self.header('do')
                    close = 'until' if keyword == 'repeat' else 'end'
                    self.statements(scope, conditional or keyword != 'do', (close,), depth+1)
                    self.take(close)
                    if close == 'until':
                        self.expression()
                    continue
                local = keyword == 'local'
                if local:
                    self.take('local')
                    if self.t.text == 'function':
                        raise ParseError('Local function skipped')
                if self.t.text in ('return', 'break', 'end', 'else', 'elseif', 'until'):
                    raise ParseError('Unsupported statement')
                target = self.target()
                if not local and (self.t.text in ('(', ':', '{') or self.t.kind == 'string'):
                    self.i = start
                    expression = self.expression()
                    if not isinstance(expression,dict) or '$call' not in expression or self.t.text == '=':
                        raise ParseError('Unsupported call-result assignment or statement')
                    for call in self.calls[call_checkpoint:]:
                        if call['start'] == self.tokens[start].start and call['end'] == self.tokens[self.i-1].end:
                            call['context'] = 'statement'
                    self.warn(line, 'standalone_call', 'Standalone call recorded without execution')
                    continue
                targets = [target]
                while self.t.text == ',':
                    self.take(',')
                    targets.append(self.target())
                values = []
                rhs_start = self.i + 1
                if self.t.text == '=':
                    self.take('=')
                    values.append(self.expression())
                    while self.t.text == ',':
                        self.take(',')
                        values.append(self.expression())
                elif not local:
                    raise ParseError('Expected =')
                rhs_source = self.slice(rhs_start) if values else ''
                boundaries = (';', '', 'local', 'function', 'if', 'for', 'while',
                              'repeat', 'do', 'return', 'break', *stops)
                if self.t.text not in boundaries and self.t.line == self.tokens[self.i-1].line:
                    # Allow another ordinary assignment on the same line.
                    probe = self.i
                    probe_calls = len(self.calls)
                    try:
                        self.target()
                        if self.t.text not in ('(', ':', '{') and self.t.kind != 'string':
                            self.take('=')
                    except ParseError:
                        raise ParseError('Unsupported assignment suffix') from None
                    finally:
                        self.i = probe
                        del self.calls[probe_calls:]
                for index, target in enumerate(targets):
                    if index < len(values):
                        value = values[index]
                    elif values and isinstance(values[-1], dict) and any(k in values[-1] for k in ('$call', '$expr')):
                        value = {'$expr': rhs_source}
                        self.warn(line, 'multi_return', 'Additional return value remains unresolved')
                    else:
                        value = None
                    self.assignments.append(dict(target=('local:' if local else '') + target,
                                                 line=line, value=value,
                                                 scope=scope, conditional=conditional,
                                                 start=self.tokens[start].start,
                                                 end=self.tokens[self.i-1].end))
            except (ParseError, RecursionError, ValueError, OverflowError) as error:
                del self.calls[call_checkpoint:]
                self.warn(line, 'unsupported', str(error) if isinstance(error, ParseError) else 'Value or nesting limit exceeded')
                self.skip(start, stops)
                if self.i == start: self.i += 1

    def parse(self):
        self.statements()
        calls = sorted(self.calls, key=lambda call: (call['start'], -call['end']))
        parents = []
        for index, call in enumerate(calls):
            while parents and not (parents[-1]['start'] <= call['start'] and call['end'] <= parents[-1]['end']):
                parents.pop()
            call['id'] = index
            call['parent_id'] = parents[-1]['id'] if parents else None
            parents.append(call)
        return ParseResult(format_version=FORMAT_VERSION, file=self.label,
                           assignments=self.assignments, functions=self.functions,
                           warnings=self.warnings, calls=calls,
                           call_format_version=CALL_FORMAT_VERSION)


def parse_text(source, file='<memory>'):
    return Parser(source, file).parse()


def parse_file(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('cp1251')
        return parse_text(text, path.name)
    except (OSError, UnicodeError):
        return ParseResult(format_version=FORMAT_VERSION, call_format_version=CALL_FORMAT_VERSION,
                           file=path.name, assignments=[], functions=[], calls=[],
                           warnings=[dict(file=path.name, line=1, code='input', message='Cannot read or decode input')])
