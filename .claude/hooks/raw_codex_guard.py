"""Non-executing raw Codex shell-command scanner."""

import os
import re
import shlex
import sys


class ScanError(Exception):
    pass


class RawCodex(Exception):
    pass


PUNCT = "();<>|&{}\n"
CONTROL = set(";\n|&(){}") | {"&&", "||", "|&", ";;", ";&", ";;&"}
REDIR = {">", ">>", "<", "<<", "<<<", "<>", ">&", "<&", ">|", "&>", "&>>"}
ASSIGN = re.compile(r"[A-Za-z_]\w*(?:\[[^]]+\])?=.*", re.S)
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
HEREDOC = re.compile(r"(?<!<)<<(-)?[ \t]*(?:(['\"])([A-Za-z_]\w*)\2|([A-Za-z_]\w*))")
EMBEDDED_RAW_CODEX = re.compile(
    r"(?<![A-Za-z0-9_.-])codex(?![A-Za-z0-9_.-])"
    r"(?:(?![;|&\n]).){1,512}?"
    r"(?<![A-Za-z0-9_.-])(?:exec|e)(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
EMBEDDED_CODE_RAW_CODEX = re.compile(
    r"(?<![A-Za-z0-9_.-])codex(?![A-Za-z0-9_.-])"
    r"(?:(?![;|&]).){1,512}?"
    r"(?<![A-Za-z0-9_.-])(?:exec|e)(?![A-Za-z0-9_.-])",
    re.IGNORECASE | re.DOTALL,
)
HIDE = {char: chr(0xE000 + index) for index, char in enumerate(PUNCT + "#*?[]")}
DYNAMIC, ARITHMETIC, STDIN_DATA, STDIN_STATIC = (
    chr(0xE100),
    chr(0xE101),
    chr(0xE102),
    chr(0xE103),
)
SHELL_CONSUMERS = {"sh", "bash", "zsh", "dash", "ksh", "source", "."}
NESTED_EXECUTION_CONSUMERS = SHELL_CONSUMERS - {"source", "."} | {
    "env",
    "find",
    "nice",
    "nohup",
    "xargs",
}
XARGS_EXECUTION_CONSUMERS = SHELL_CONSUMERS | {
    "arch",
    "caffeinate",
    "eval",
    "find",
    "git",
    "rg",
    "sandbox-exec",
    "script",
    "stdbuf",
    "xargs",
}
SAFE_TERMINAL_COMMANDS = {
    "cat",
    "cmp",
    "comm",
    "cp",
    "cut",
    "diff",
    "echo",
    "grep",
    "head",
    "ls",
    "mv",
    "printf",
    "rm",
    "tail",
    "touch",
    "tr",
    "uniq",
    "wc",
}
XARGS_DATA_ONLY = SAFE_TERMINAL_COMMANDS
CODEX_VALUE_OPTIONS = {
    "-a",
    "--add-dir",
    "--ask-for-approval",
    "-c",
    "-C",
    "--cd",
    "--config",
    "--disable",
    "--enable",
    "-i",
    "--image",
    "--local-provider",
    "-m",
    "--model",
    "-p",
    "--profile",
    "--remote",
    "--remote-auth-token-env",
    "-s",
    "--sandbox",
}
CODEX_FLAG_OPTIONS = {
    "--dangerously-bypass-approvals-and-sandbox",
    "--dangerously-bypass-hook-trust",
    "-h",
    "--help",
    "--no-alt-screen",
    "--oss",
    "--search",
    "--strict-config",
    "-V",
    "--version",
}


def word_start(char):
    return char.isspace() or char in PUNCT


def active_at(text, stop):
    quote = None
    start = True
    index = 0
    while index < stop:
        char = text[index]
        if char == "\\" and quote != "'" and index + 1 < stop:
            index += 2
            start = False
            continue
        if char in "'\"":
            quote = None if quote == char else char if quote is None else quote
            start = False
        elif char == "#" and quote is None and start:
            return False
        else:
            start = word_start(char)
        index += 1
    return quote is None


def strip_heredocs(command):
    lines = command.splitlines(keepends=True)
    output, bodies = [], []
    index = 0
    while index < len(lines):
        line = lines[index]
        specs = [match for match in HEREDOC.finditer(line) if active_at(line, match.start())]
        header = normalize(tokens(line)) if specs else []
        if any(item in CONTROL - {"\n"} for item in header):
            raise ScanError("unsupported compound heredoc header")
        header = [item for item in header if item not in CONTROL]
        shell_consumer = shell_stdin_consumer(header) if header else False
        output.append(line)
        index += 1
        for match in specs:
            delimiter = match.group(3) or match.group(4)
            body = []
            while index < len(lines):
                candidate = lines[index].rstrip("\r\n")
                candidate = candidate.lstrip("\t") if match.group(1) else candidate
                if candidate == delimiter:
                    index += 1
                    break
                body.append(lines[index])
                index += 1
            else:
                raise ScanError("unterminated heredoc")
            body_text = "".join(body)
            if shell_consumer and has_raw_codex(body_text):
                raise RawCodex
            if not shell_consumer and not match.group(2):
                bodies.append(body_text)
    return "".join(output), bodies


def close_substitution(text, start):
    quote, depth, index = None, 1, start + 1
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'" and index + 1 < len(text):
            index += 2
            continue
        if char in "'\"":
            quote = None if quote == char else char if quote is None else quote
        elif quote != "'" and text.startswith("$(", index):
            index = close_substitution(text, index + 1)
            continue
        elif quote is None and char == "(":
            depth += 1
        elif quote is None and char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ScanError("unclosed substitution")


def backtick_end(text, start):
    index = start + 1
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            index += 2
        elif text[index] == "`":
            return index + 1
        else:
            index += 1
    raise ScanError("unclosed backtick")


def brace_expansion_end(text, start):
    quote, depth, separator, index = None, 1, False, start + 1
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'" and index + 1 < len(text):
            index += 2
            continue
        if quote != "'" and text.startswith("$(", index):
            index = close_substitution(text, index + 1)
            continue
        if quote is None and text.startswith(("<(", ">("), index):
            index = close_substitution(text, index + 1)
            continue
        if quote != "'" and char == "`":
            index = backtick_end(text, index)
            continue
        if char in "'\"":
            quote = None if quote == char else char if quote is None else quote
        elif quote is None:
            if char.isspace() or char in ";|&\n":
                return None
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index + 1 if separator else None
            elif char == "," or text.startswith("..", index):
                separator = True
        index += 1
    return None


def prepare(command):
    output = []
    quote = None
    start = True
    index = 0
    while index < len(command):
        char = command[index]
        if quote is None and command.startswith("{}", index):
            output.append(HIDE["{"] + HIDE["}"])
            index += 2
            start = False
            continue
        brace_end = brace_expansion_end(command, index) if quote is None and char == "{" else None
        if brace_end is not None:
            prepare(command[index + 1 : brace_end - 1])
            output.append(DYNAMIC)
            index = brace_end
            start = False
            continue
        if char == "\\" and quote != "'" and index + 1 < len(command):
            escaped = command[index + 1]
            if escaped == "\n":
                index += 2
                continue
            output.append(HIDE.get(escaped, char + escaped))
            index += 2
            start = False
            continue
        if char == "#" and quote is None and start:
            end = command.find("\n", index)
            if end < 0:
                break
            output.append("\n")
            index = end + 1
            start = True
            continue
        variable = re.match(r"\$\{([A-Za-z_]\w*)\}", command[index:]) if quote != "'" else None
        if variable:
            output.append("$" + HIDE["{"] + variable.group(1) + HIDE["}"])
            index += len(variable.group())
            start = False
            continue
        if quote != "'" and command.startswith("${", index):
            end = command.find("}", index + 2)
            if end < 0:
                raise ScanError("unclosed parameter expansion")
            prepare(command[index + 2 : end])
            output.append(DYNAMIC)
            index = end + 1
            start = False
            continue
        dynamic = quote != "'" and command.startswith("$(", index)
        process = quote is None and command.startswith(("<(", ">("), index)
        if dynamic or process:
            arithmetic = dynamic and command.startswith("$((", index)
            open_at = index + 1
            end = close_substitution(command, open_at)
            body = command[open_at + 1 : end - 1]
            if arithmetic:
                prepare(body)
                output.append(ARITHMETIC)
            else:
                if has_raw_codex(body):
                    raise RawCodex
                output.append(DYNAMIC)
            index = end
            start = False
            continue
        if quote != "'" and char == "`":
            end = backtick_end(command, index)
            if has_raw_codex(command[index + 1 : end - 1]):
                raise RawCodex
            output.append(DYNAMIC)
            index = end
            start = False
            continue
        if quote is None and command.startswith("$'", index):
            end = command.find("'", index + 2)
            if end < 0:
                raise ScanError("unclosed ANSI-C quote")
            output.append(DYNAMIC)
            index = end + 1
            start = False
            continue
        if char in "'\"":
            quote = None if quote == char else char if quote is None else quote
            output.append(char)
            start = False
        elif quote is not None and char in HIDE:
            output.append(HIDE[char])
        elif char == "#" and quote is None:
            output.append(HIDE["#"])
        else:
            output.append(char)
            start = word_start(char)
        index += 1
    return "".join(output)


def tokens(command):
    lexer = shlex.shlex(prepare(command), posix=True, punctuation_chars=PUNCT)
    lexer.whitespace, lexer.whitespace_split, lexer.commenters = " \t\r", True, ""
    operators = (
        "<<<",
        "&>>",
        ";;&",
        "&&",
        "||",
        ">>",
        "<<",
        "<>",
        ">&",
        "<&",
        ">|",
        "&>",
        ";;",
        ";&",
        "|&",
    )
    result = []
    for token in lexer:
        if token and set(token) <= set(PUNCT):
            while token:
                part = next((item for item in operators if token.startswith(item)), token[0])
                result.append(part)
                token = token[len(part) :]
        else:
            result.append(token)
    return result


def after_parens(items, start, doubled=False):
    depth, index = 0, start + (2 if doubled else 1)
    while index < len(items):
        depth += items[index] == "("
        if items[index] == ")":
            if doubled and depth == 0 and items[index : index + 2] == [")", ")"]:
                return index + 2
            if not doubled and depth == 0:
                return index + 1
            depth -= bool(depth)
        index += 1
    raise ScanError("unclosed inert construct")


def normalize(items):
    inert, index = [], 0
    while index < len(items):
        item = items[index]
        if ASSIGN.fullmatch(item) and item.endswith("=") and items[index + 1 : index + 2] == ["("]:
            inert.append(item + "ARRAY")
            index = after_parens(items, index + 1)
        elif item.endswith("$") and items[index + 1 : index + 3] == ["(", "("]:
            inert.append(item[:-1] + "0")
            index = after_parens(items, index + 1, True)
        elif items[index : index + 2] == ["(", "("]:
            inert.append("true")
            index = after_parens(items, index, True)
        else:
            inert.append(item)
            index += 1
    result, index = [], 0
    while index < len(inert):
        named_fd = inert[index : index + 4]
        operator = None
        stdin_fd = True
        if (
            len(named_fd) == 4
            and named_fd[0] == "{"
            and named_fd[2] == "}"
            and named_fd[3] in REDIR
        ):
            operator = named_fd[3]
            stdin_fd = False
            index += 4
        elif inert[index] in REDIR:
            operator = inert[index]
            if result and result[-1].isdigit():
                stdin_fd = result.pop() == "0"
            index += 1
        else:
            result.append(inert[index])
            index += 1
            continue
        if index >= len(inert) or inert[index] in CONTROL | REDIR:
            raise ScanError("redirection without target")
        target = inert[index]
        if stdin_fd and operator == "<<<":
            result.append(STDIN_STATIC + target)
        elif (
            stdin_fd
            and operator in {"<", "<>", "<&"}
            and (DYNAMIC in target or "$" in reveal(target))
        ):
            result.append(STDIN_DATA)
        index += 1
    return result


def reveal(value):
    for plain, hidden in HIDE.items():
        value = value.replace(hidden, plain)
    return value


def codex_first_positional(argv):
    position = 0
    short_values = {item for item in CODEX_VALUE_OPTIONS if item.startswith("-") and len(item) == 2}
    long_values = {item for item in CODEX_VALUE_OPTIONS if item.startswith("--")}
    while position < len(argv):
        raw = argv[position]
        item = reveal(raw)
        if DYNAMIC in raw or "$" in item or any(char in raw for char in "*?["):
            raise ScanError("dynamic Codex global option")
        if item == "--":
            return reveal(argv[position + 1]) if position + 1 < len(argv) else None
        if item in CODEX_VALUE_OPTIONS:
            position += 2
            if position > len(argv):
                raise ScanError("Codex global option without value")
        elif item in CODEX_FLAG_OPTIONS:
            position += 1
        elif any(item.startswith(option + "=") for option in long_values) or any(
            item.startswith(option) and item != option for option in short_values
        ):
            position += 1
        elif item.startswith("-"):
            raise ScanError("unsupported Codex global option")
        else:
            return item
    return None


def data_only_command(executable, args):
    return executable in SAFE_TERMINAL_COMMANDS | {
        "find",
        "rg",
        "sort",
    } or (executable == "git" and args[:1] == ["grep"])


def code_option_payloads(raw_args, options):
    payloads = []
    for position, raw in enumerate(raw_args):
        item = reveal(raw)
        if item in options:
            if position + 1 < len(raw_args):
                payloads.append(raw_args[position + 1])
            continue
        for option in options:
            if item.startswith(option) and item != option:
                payloads.append(raw[len(option) :])
                break
    return payloads


def clustered_code_payloads(raw_args, pattern):
    payloads = []
    for position, raw in enumerate(raw_args):
        match = re.fullmatch(pattern, reveal(raw), re.DOTALL)
        if match is None:
            continue
        attached = match.group(1)
        if attached:
            payloads.append(attached)
        elif position + 1 < len(raw_args):
            payloads.append(raw_args[position + 1])
    return payloads


def embedded_code_payloads(executable, raw_args):
    if executable.startswith("python"):
        return clustered_code_payloads(raw_args, r"-[bBdEhiIOPqRsSuvVx]*c(.*)")
    if executable.startswith("perl"):
        return clustered_code_payloads(raw_args, r"-[CDSTUWXcdlnpsuvw]*[eE](.*)")
    if executable.startswith("ruby"):
        return clustered_code_payloads(raw_args, r"-[Wacdhlnpsvwy]*e(.*)")
    if executable in {"node", "nodejs"}:
        return clustered_code_payloads(raw_args, r"-[cip]*[pe](.*)") + code_option_payloads(
            raw_args, {"--eval", "--print"}
        )
    if executable == "php":
        return clustered_code_payloads(raw_args, r"-[CHnqsw]*r(.*)")
    if executable == "osascript":
        return code_option_payloads(raw_args, {"-e"})
    if executable in {"awk", "gawk", "mawk", "nawk"} and not any(
        reveal(item) in {"-f", "--file"} or reveal(item).startswith("--file=") for item in raw_args
    ):
        return raw_args
    return ()


def find_placeholder(value):
    return "{}" in reveal(value)


def find_command_index(argv):
    index = command_index(argv)
    while index is not None and index < len(argv):
        if os.path.basename(reveal(argv[index])) != "arch":
            return index
        index += 1
        while index < len(argv):
            option = reveal(argv[index])
            if option == "--":
                index += 1
                break
            if option in {"-e", "-arch"}:
                if index + 1 >= len(argv):
                    raise ScanError("arch option without value")
                index += 2
            elif option.startswith("-"):
                index += 1
            else:
                break
        if index > len(argv):
            raise ScanError("arch option without value")
        if index >= len(argv):
            return index
        nested = command_index(argv[index:])
        if nested is None:
            return None
        index += nested
    return index


def find_executor_has_raw_codex(command):
    if raw_argv(command):
        return True
    command_at = find_command_index(command)
    placeholders = [position for position, item in enumerate(command) if find_placeholder(item)]
    if not placeholders:
        return False
    if command_at is None or command_at >= len(command):
        raise ScanError("find placeholder supplies an executable")
    if find_placeholder(command[command_at]):
        raise ScanError("find placeholder supplies an executable")
    target = os.path.basename(reveal(command[command_at]))
    target_args = command[command_at + 1 :]
    if target in SAFE_TERMINAL_COMMANDS or target == "sort":
        return False
    if target == "codex":
        subcommand = codex_first_positional(target_args)
        if subcommand in {"exec", "e"}:
            return True
        if subcommand is not None and "{}" in subcommand:
            raise ScanError("find placeholder supplies a Codex subcommand")
        return False
    if target in SHELL_CONSUMERS - {"source", "."}:
        for position, option in enumerate(target_args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", reveal(option)):
                payload_at = command_at + position + 2
                if payload_at >= len(command) or any(
                    placeholder <= payload_at for placeholder in placeholders
                ):
                    raise ScanError("find placeholder supplies a shell payload")
                return False
        raise ScanError("find placeholder supplies shell arguments")
    if target in XARGS_EXECUTION_CONSUMERS | NESTED_EXECUTION_CONSUMERS:
        raise ScanError("find placeholder supplies executable arguments")
    return False


def command_index(argv):
    index = 0
    first = reveal(argv[0]) if argv else ""
    if first in {"case", "esac"}:
        raise ScanError("unsupported case compound")
    if first in {"for", "select", "function"}:
        return None
    while index < len(argv) and reveal(argv[index]) in {
        "if",
        "then",
        "elif",
        "else",
        "while",
        "until",
        "do",
        "!",
    }:
        index += 1
    if index < len(argv) and reveal(argv[index]) in {"fi", "done"}:
        return None
    if index < len(argv) and reveal(argv[index]) == "coproc":
        index += 1
    while index < len(argv) and ASSIGN.fullmatch(reveal(argv[index])):
        index += 1
    while index < len(argv):
        wrapper = os.path.basename(reveal(argv[index]))
        if wrapper == "env":
            index += 1
            while index < len(argv):
                item = reveal(argv[index])
                if ASSIGN.fullmatch(item) or item in {"-v", "-i", "-0"}:
                    index += 1
                elif item in {"-u", "-C", "-P"}:
                    index += 2
                elif re.match(r"^-[uCP].+", item) or item.startswith("--chdir="):
                    index += 1
                elif item == "-S":
                    if index + 1 >= len(argv) or "\\_" in reveal(argv[index + 1]):
                        raise ScanError("unsupported env split-string")
                    argv[index : index + 2] = shlex.split(reveal(argv[index + 1]))
                elif item == "--":
                    index += 1
                    break
                elif item.startswith("-"):
                    raise ScanError("unsupported env option")
                else:
                    break
        elif wrapper == "command":
            index += 1
            while index < len(argv) and reveal(argv[index]).startswith("-"):
                item = reveal(argv[index])
                if item in {"-v", "-V"}:
                    return None
                if item not in {"-p", "--"}:
                    raise ScanError("unsupported command option")
                index += 1
        elif wrapper == "builtin":
            index += 1
            if index < len(argv) and reveal(argv[index]) == "--":
                index += 1
        elif wrapper == "exec":
            index += 1
            while index < len(argv) and reveal(argv[index]).startswith("-"):
                item = reveal(argv[index])
                if item == "--":
                    index += 1
                    break
                if item == "-a":
                    index += 2
                elif item.startswith("-a") or re.fullmatch(r"-[cl]+", item):
                    index += 1
                else:
                    raise ScanError("unsupported exec option")
        elif wrapper == "nohup":
            index += 1
            if index < len(argv) and reveal(argv[index]) == "--":
                index += 1
        elif wrapper == "time":
            index += 1
            if index < len(argv) and reveal(argv[index]) == "-p":
                index += 1
            while index < len(argv) and ASSIGN.fullmatch(reveal(argv[index])):
                index += 1
            while index < len(argv) and reveal(argv[index]) == "!":
                index += 1
            while index < len(argv) and ASSIGN.fullmatch(reveal(argv[index])):
                index += 1
        elif wrapper == "nice":
            index += 1
            if index < len(argv) and reveal(argv[index]) == "--":
                index += 1
            elif index < len(argv) and reveal(argv[index]) == "-n":
                index += 2
            elif index < len(argv) and re.fullmatch(r"-n?\d+", reveal(argv[index])):
                index += 1
            elif index < len(argv) and reveal(argv[index]).startswith("--adjustment="):
                index += 1
        else:
            break
        if index > len(argv):
            raise ScanError("missing wrapper operand")
        if index < len(argv) and reveal(argv[index]).startswith("-"):
            raise ScanError("unsupported wrapper option")
    return index


def shell_stdin_consumer(argv):
    index = command_index(argv)
    if index is None or index >= len(argv):
        return False
    raw_word = argv[index]
    word = reveal(raw_word)
    if DYNAMIC in raw_word or "$" in word or any(char in raw_word for char in "*?["):
        raise ScanError("dynamic stdin consumer")
    executable = os.path.basename(word)
    raw_args = argv[index + 1 :]
    args = [reveal(item) for item in raw_args]
    if executable in SHELL_CONSUMERS:
        return True
    if executable == "eval":
        payload_args = raw_args[1:] if args[:1] == ["--"] else raw_args
        payload = " ".join(payload_args)
        if DYNAMIC in payload or "$" in reveal(payload):
            raise ScanError("dynamic eval payload")
        stream = normalize(tokens(payload))
        current = []
        for item in stream + [";"]:
            if item in CONTROL:
                if current and shell_stdin_consumer(current):
                    return True
                current = []
            else:
                current.append(item)
        return False
    if data_only_command(executable, args):
        return False
    return any(
        os.path.basename(reveal(item)) in NESTED_EXECUTION_CONSUMERS
        and DYNAMIC not in item
        and "$" not in reveal(item)
        and not any(char in item for char in "*?[")
        and shell_stdin_consumer(raw_args[position:])
        for position, item in enumerate(raw_args)
    )


def raw_argv(argv, stdin_dynamic=False, stdin_payloads=()):
    stdin_payloads = tuple(stdin_payloads) + tuple(
        item[len(STDIN_STATIC) :] for item in argv if item.startswith(STDIN_STATIC)
    )
    stdin_dynamic = stdin_dynamic or STDIN_DATA in argv
    argv = [item for item in argv if item != STDIN_DATA and not item.startswith(STDIN_STATIC)]
    index = command_index(argv)
    if index is None or index >= len(argv):
        return False
    raw_word = argv[index]
    raw_args = argv[index + 1 :]
    word = reveal(raw_word)
    args = [reveal(item) for item in raw_args]
    exact = any(item in {"exec", "e"} for item in args)
    codex = os.path.basename(word) == "codex" or any(
        "CODEX" in (match.group(1) or match.group(2)).upper() for match in VARIABLE.finditer(word)
    )
    if codex and exact:
        return True
    if DYNAMIC in raw_word or "$" in word or any(char in raw_word for char in "*?["):
        raise ScanError("dynamic executable")
    if codex and any(
        DYNAMIC in raw or "$" in args[position] or any(char in raw for char in "*?[")
        for position, raw in enumerate(raw_args)
    ):
        raise ScanError("dynamic Codex subcommand")
    executable = os.path.basename(word)
    if executable == "sort" and any(
        option == "--compress-program" or option.startswith("--compress-program=")
        for option in args
    ):
        raise ScanError("sort may execute an external compressor")
    if executable in SHELL_CONSUMERS - {"source", "."}:
        for position, option in enumerate(args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", option):
                if (
                    position + 1 >= len(args)
                    or DYNAMIC in args[position + 1]
                    or "$" in args[position + 1]
                ):
                    raise ScanError("dynamic shell payload")
                return has_raw_codex(
                    raw_args[position + 1],
                    stdin_dynamic=stdin_dynamic,
                    stdin_payloads=stdin_payloads,
                )
    if executable in SHELL_CONSUMERS:
        for payload in stdin_payloads:
            if has_raw_codex(payload):
                raise RawCodex
        if stdin_dynamic or any(DYNAMIC in item for item in raw_args):
            raise RawCodex
    if executable == "eval":
        payload_args = raw_args[1:] if args[:1] == ["--"] else raw_args
        payload = " ".join(payload_args)
        if DYNAMIC in payload or "$" in reveal(payload):
            raise ScanError("dynamic eval payload")
        return has_raw_codex(
            payload,
            stdin_dynamic=stdin_dynamic,
            stdin_payloads=stdin_payloads,
        )
    if executable == "xargs":
        position = 0
        while position < len(args) and args[position].startswith("-"):
            option = args[position]
            if option in {"-0", "--null"} or re.fullmatch(r"-n\d+", option):
                position += 1
            elif option in {"-n", "--max-args"}:
                position += 2
            elif option == "--":
                position += 1
                break
            else:
                raise ScanError("unsupported xargs option")
        command = raw_args[position:]
        if not command:
            return False
        command_at = command_index(command)
        if command_at is None or command_at >= len(command):
            raise ScanError("xargs supplies a dynamic executable")
        target = os.path.basename(reveal(command[command_at]))
        if target == "codex":
            subcommand = codex_first_positional(command[command_at + 1 :])
            if subcommand in {"exec", "e"}:
                return True
            if subcommand is None:
                raise ScanError("xargs supplies dynamic Codex arguments")
            return False
        if raw_argv(command):
            return True
        target_args = [reveal(item) for item in command[command_at + 1 :]]
        if target in SHELL_CONSUMERS - {"source", "."}:
            if any(
                re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", option) and position + 1 < len(target_args)
                for position, option in enumerate(target_args)
            ):
                return False
            raise ScanError("xargs supplies dynamic shell arguments")
        if target in XARGS_EXECUTION_CONSUMERS:
            raise ScanError("xargs supplies dynamic executable arguments")
        if target in XARGS_DATA_ONLY:
            return False
        raise ScanError("xargs supplies arguments to an unknown command")
    if executable == "find":
        for position, item in enumerate(args):
            if item in {"-exec", "-execdir", "-ok", "-okdir"}:
                end = next(
                    (at for at in range(position + 1, len(args)) if args[at] in {";", "+"}),
                    len(args),
                )
                if end == len(args):
                    raise ScanError("unterminated find executor")
                if find_executor_has_raw_codex(raw_args[position + 1 : end]):
                    return True
    if executable == "rg":
        for position, option in enumerate(args):
            payload = None
            if option == "--pre":
                if position + 1 >= len(raw_args):
                    raise ScanError("rg --pre without command")
                payload = raw_args[position + 1]
            elif option.startswith("--pre="):
                payload = raw_args[position][len("--pre=") :]
            if payload is not None:
                if DYNAMIC in payload or "$" in reveal(payload):
                    raise ScanError("dynamic rg preprocessor")
                if has_raw_codex(payload):
                    return True
    if executable == "git" and args[:1] == ["grep"]:
        for position, option in enumerate(args[1:], start=1):
            payload = None
            if option in {"-O", "--open-files-in-pager"}:
                raise ScanError("dynamic git grep pager")
            if option.startswith("-O") and option != "-O":
                payload = raw_args[position][2:]
            elif option.startswith("--open-files-in-pager="):
                payload = raw_args[position].split("=", 1)[1]
            if payload is not None:
                if DYNAMIC in payload or "$" in reveal(payload):
                    raise ScanError("dynamic git grep pager")
                if has_raw_codex(payload):
                    return True
    data_only = data_only_command(executable, args)
    nested_checked = False
    if not data_only:
        for position, item in enumerate(raw_args):
            nested = reveal(item)
            suffix = raw_args[position:]
            if (
                os.path.basename(nested) in NESTED_EXECUTION_CONSUMERS
                and DYNAMIC not in item
                and "$" not in nested
                and not any(char in item for char in "*?[")
            ):
                nested_checked = True
                if raw_argv(suffix, stdin_dynamic, stdin_payloads):
                    return True
    if (
        not data_only
        and not nested_checked
        and (
            any(EMBEDDED_RAW_CODEX.search(reveal(item)) for item in raw_args)
            or any(
                EMBEDDED_CODE_RAW_CODEX.search(reveal(item))
                for item in embedded_code_payloads(executable, raw_args)
            )
        )
    ):
        raise ScanError("embedded code may invoke raw Codex")
    literal_raw = any(
        os.path.basename(reveal(item)) == "codex"
        and DYNAMIC not in item
        and "$" not in reveal(item)
        and any(reveal(later) in {"exec", "e"} for later in raw_args[position + 1 :])
        for position, item in enumerate(raw_args)
    )
    if literal_raw and not data_only and not ASSIGN.fullmatch(word):
        raise ScanError("unknown command may remap raw Codex invocation")
    dynamic_raw = any(
        (DYNAMIC in item or "$" in reveal(item) or any(char in item for char in "*?["))
        and any(reveal(later) in {"exec", "e"} for later in raw_args[position + 1 :])
        for position, item in enumerate(raw_args)
    )
    if dynamic_raw and not data_only and not ASSIGN.fullmatch(word):
        raise ScanError("unknown command may remap dynamic executable")
    return False


def has_raw_codex(command, stdin_dynamic=False, stdin_payloads=()):
    command, bodies = strip_heredocs(command)
    for body in bodies:
        prepare(body)
    stream = normalize(tokens(command))
    segments, current, current_taint = [], [], False
    punctuation_scopes, word_scopes = [], []
    pending_pipe = False
    for item in stream + [";"]:
        if item in CONTROL:
            if current:
                segments.append((current, current_taint))
                closer = reveal(current[0])
                if word_scopes and word_scopes[-1][0] == closer:
                    word_scopes.pop()
                current = []
            if item in {"|", "|&"}:
                pending_pipe = True
            elif item in {"(", "{"}:
                tainted = (
                    stdin_dynamic
                    or pending_pipe
                    or any(taint for _, taint in punctuation_scopes + word_scopes)
                )
                punctuation_scopes.append((")" if item == "(" else "}", tainted))
                pending_pipe = False
            elif item in {")", "}"}:
                if punctuation_scopes and punctuation_scopes[-1][0] == item:
                    punctuation_scopes.pop()
                pending_pipe = False
            elif item != "\n":
                pending_pipe = False
        else:
            if not current:
                active_taint = (
                    stdin_dynamic
                    or pending_pipe
                    or any(taint for _, taint in punctuation_scopes + word_scopes)
                )
                word = reveal(item)
                if word in {"if", "while", "until", "for", "select"}:
                    closer = "fi" if word == "if" else "done"
                    word_scopes.append((closer, active_taint))
                current_taint = active_taint
                pending_pipe = False
            current.append(item)
    return any(
        raw_argv(argv, segment_stdin_dynamic, stdin_payloads)
        for argv, segment_stdin_dynamic in segments
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        return 2
    try:
        return 0 if has_raw_codex(argv[0]) else 1
    except RawCodex:
        return 0
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
