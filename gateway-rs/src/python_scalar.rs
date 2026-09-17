use std::sync::OnceLock;

const DEFAULT_INTEGER_DIGIT_LIMIT: usize = 4300;
const MODEL_INTEGER_CHARACTER_LIMIT: usize = 4300;
const INVALID_DIGIT_LIMIT: &str =
    "PYTHONINTMAXSTRDIGITS must be 0 or an integer from 640 to 2147483647";

// Decimal-digit blocks observed in the retained Python reference image
// (unicodedata 15.0.0). Each block contains the ten digits in order.
const DECIMAL_ZEROS: &[u32] = &[
    0x30, 0x660, 0x6f0, 0x7c0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66, 0xbe6, 0xc66, 0xce6, 0xd66,
    0xde6, 0xe50, 0xed0, 0xf20, 0x1040, 0x1090, 0x17e0, 0x1810, 0x1946, 0x19d0, 0x1a80, 0x1a90,
    0x1b50, 0x1bb0, 0x1c40, 0x1c50, 0xa620, 0xa8d0, 0xa900, 0xa9d0, 0xa9f0, 0xaa50, 0xabf0, 0xff10,
    0x104a0, 0x10d30, 0x11066, 0x110f0, 0x11136, 0x111d0, 0x112f0, 0x11450, 0x114d0, 0x11650,
    0x116c0, 0x11730, 0x118e0, 0x11950, 0x11c50, 0x11d50, 0x11da0, 0x11f50, 0x16a60, 0x16ac0,
    0x16b50, 0x1d7ce, 0x1d7d8, 0x1d7e2, 0x1d7ec, 0x1d7f6, 0x1e140, 0x1e2f0, 0x1e4f0, 0x1e950,
    0x1fbf0,
];

fn decimal_digit(character: char) -> Option<u8> {
    let codepoint = u32::from(character);
    let index = DECIMAL_ZEROS
        .partition_point(|zero| *zero <= codepoint)
        .checked_sub(1)?;
    let digit = codepoint - DECIMAL_ZEROS[index];
    (digit < 10).then_some(digit as u8)
}

fn integer_whitespace(character: char) -> bool {
    matches!(character,
        '\u{9}'..='\u{d}' | ' ' | '\u{85}' | '\u{a0}' | '\u{1680}' |
        '\u{2000}'..='\u{200a}' | '\u{2028}' | '\u{2029}' | '\u{202f}' |
        '\u{205f}' | '\u{3000}')
}

/// Python str.strip() additionally accepts ASCII information separators.
pub(crate) fn strip(value: &str) -> &str {
    value.trim_matches(|character| {
        integer_whitespace(character) || matches!(character, '\u{1c}'..='\u{1f}')
    })
}

/// Match Python int(string)'s decimal grammar within the i128 representation.
/// Python's unbounded integer range remains a separate compatibility gap.
pub(crate) fn parse_integer(value: &str) -> Option<i128> {
    parse_integer_with_limit(value, integer_digit_limit().ok()?)
}

/// Pydantic v1 additionally bounds the entire untrimmed string by characters.
pub(crate) fn parse_model_integer(value: &str) -> Option<i128> {
    parse_model_integer_with_limit(value, integer_digit_limit().ok()?)
}

fn parse_model_integer_with_limit(value: &str, digit_limit: usize) -> Option<i128> {
    if value
        .chars()
        .take(MODEL_INTEGER_CHARACTER_LIMIT + 1)
        .count()
        > MODEL_INTEGER_CHARACTER_LIMIT
    {
        return None;
    }
    parse_integer_with_limit(value, digit_limit)
}

/// Capture the interpreter-style setting once per process, including errors.
pub(crate) fn integer_digit_limit() -> Result<usize, &'static str> {
    static LIMIT: OnceLock<Result<usize, &'static str>> = OnceLock::new();
    *LIMIT.get_or_init(|| match std::env::var("PYTHONINTMAXSTRDIGITS") {
        Ok(value) => parse_digit_limit(Some(&value)),
        Err(std::env::VarError::NotPresent) => parse_digit_limit(None),
        Err(std::env::VarError::NotUnicode(_)) => Err(INVALID_DIGIT_LIMIT),
    })
}

fn parse_digit_limit(value: Option<&str>) -> Result<usize, &'static str> {
    let Some(value) = value.filter(|value| !value.is_empty()) else {
        return Ok(DEFAULT_INTEGER_DIGIT_LIMIT);
    };
    // CPython's C integer parser accepts leading ASCII whitespace and a sign,
    // but rejects trailing whitespace, Unicode digits, and digit separators.
    let value = value.trim_start_matches(|character| matches!(character, '\u{9}'..='\u{d}' | ' '));
    let digits = value.strip_prefix(['+', '-']).unwrap_or(value);
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(INVALID_DIGIT_LIMIT);
    }
    let limit: i32 = value.parse().map_err(|_| INVALID_DIGIT_LIMIT)?;
    if limit != 0 && limit < 640 {
        return Err(INVALID_DIGIT_LIMIT);
    }
    usize::try_from(limit).map_err(|_| INVALID_DIGIT_LIMIT)
}

fn parse_integer_with_limit(value: &str, digit_limit: usize) -> Option<i128> {
    let value = value.trim_matches(integer_whitespace);
    let mut normalized = String::with_capacity(value.len());
    let mut previous_digit = false;
    let mut digits = 0;
    for (index, character) in value.chars().enumerate() {
        if let Some(digit) = decimal_digit(character) {
            digits += 1;
            if digit_limit != 0 && digits > digit_limit {
                return None;
            }
            normalized.push(char::from(b'0' + digit));
            previous_digit = true;
        } else if index == 0 && matches!(character, '+' | '-') {
            normalized.push(character);
        } else if character == '_' && previous_digit {
            previous_digit = false;
        } else {
            return None;
        }
    }
    if !previous_digit {
        return None;
    }
    normalized.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn integer_digit_limit_configuration_matches_python_startup() {
        assert_eq!(parse_digit_limit(None), Ok(4300));
        for (value, limit) in [
            ("", 4300),
            ("0", 0),
            ("640", 640),
            ("4300", 4300),
            ("0640", 640),
            ("+640", 640),
            ("-0", 0),
            ("-0000", 0),
            ("0000", 0),
            (" 640", 640),
            (" +640", 640),
            ("\u{b}640", 640),
            ("2147483647", 2147483647),
        ] {
            assert_eq!(parse_digit_limit(Some(value)), Ok(limit), "{value:?}");
        }
        for value in [
            "1",
            "639",
            "-1",
            "-640",
            "invalid",
            "٠",
            "1_000",
            "640 ",
            "640\n",
            " +640 ",
            " ",
            "+",
            "2147483648",
        ] {
            assert_eq!(
                parse_digit_limit(Some(value)),
                Err(INVALID_DIGIT_LIMIT),
                "{value:?}"
            );
        }
    }

    #[test]
    fn model_character_and_interpreter_digit_limits_match_python() {
        for zero in ["0", "٠"] {
            let padded = |digits: usize| format!("{}120", zero.repeat(digits - 3));
            let boundary = padded(4300);
            assert_eq!(parse_model_integer_with_limit(&boundary, 4300), Some(120));
            assert_eq!(
                parse_model_integer_with_limit(&format!("+{boundary}"), 4300),
                None
            );
            assert_eq!(
                parse_model_integer_with_limit(&format!(" {} ", padded(4298)), 4300),
                Some(120)
            );
            assert_eq!(
                parse_model_integer_with_limit(&format!(" {} ", padded(4299)), 4300),
                None
            );
            let separated = padded(2151)
                .chars()
                .map(|character| character.to_string())
                .collect::<Vec<_>>()
                .join("_");
            assert_eq!(parse_integer_with_limit(&separated, 4300), Some(120));
            assert_eq!(parse_model_integer_with_limit(&separated, 4300), None);
            assert_eq!(parse_integer_with_limit(&padded(4301), 4300), None);
            assert_eq!(parse_integer_with_limit(&padded(4301), 0), Some(120));
            assert_eq!(parse_integer_with_limit(&padded(4301), 5000), Some(120));
            assert_eq!(parse_model_integer_with_limit(&padded(4301), 0), None);
            assert_eq!(parse_model_integer_with_limit(&padded(4301), 5000), None);
            assert_eq!(parse_model_integer_with_limit(&padded(640), 640), Some(120));
            assert_eq!(parse_model_integer_with_limit(&padded(641), 640), None);
            let separated = padded(640)
                .chars()
                .map(|character| character.to_string())
                .collect::<Vec<_>>()
                .join("_");
            assert_eq!(
                parse_model_integer_with_limit(&format!(" +{separated} "), 640),
                Some(120)
            );
        }
    }

    #[test]
    fn decimal_integer_grammar_matches_python_across_digit_blocks() {
        for zero in DECIMAL_ZEROS {
            let digit = |offset| char::from_u32(zero + offset).unwrap();
            let value = format!("{}{}{}", digit(1), digit(2), digit(0));
            assert_eq!(parse_integer(&value), Some(120));
            assert_eq!(
                parse_integer(&format!(
                    "\u{a0}+{}_{}{}\u{3000}",
                    digit(1),
                    digit(2),
                    digit(0)
                )),
                Some(120)
            );
            assert_eq!(parse_integer(&format!("1_{}0", digit(2))), Some(120));
            for value in [
                format!("_{value}"),
                format!("{value}_"),
                format!("{}__{}", digit(1), digit(2)),
            ] {
                assert_eq!(parse_integer(&value), None);
            }
        }
        for (value, expected) in [
            ("-١٢٠", -120),
            ("٥٩", 59),
            ("００６０", 60),
            ("+1_200", 1200),
            ("\u{85}120\u{85}", 120),
            ("-0", 0),
        ] {
            assert_eq!(parse_integer(value), Some(expected));
        }
        for value in [
            "",
            " ",
            "+",
            "-",
            "1__20",
            "+_120",
            "١ ٢٠",
            "−١٢٠",
            "²⁶⁰",
            "①②⓪",
            "120.0",
            "1e2",
            "0x78",
            "\u{1c}120\u{1f}",
            "\u{200b}120\u{200b}",
            "\u{feff}120",
            "\u{10d40}20",
        ] {
            assert_eq!(parse_integer(value), None, "{value:?}");
        }
        assert_eq!(parse_integer(&i128::MIN.to_string()), Some(i128::MIN));
        assert_eq!(parse_integer(&i128::MAX.to_string()), Some(i128::MAX));
        assert_eq!(
            parse_integer("170141183460469231731687303715884105728"),
            None
        );
    }

    #[test]
    fn model_and_environment_whitespace_match_python_distinction() {
        for character in ['\u{1c}', '\u{1d}', '\u{1e}', '\u{1f}'] {
            let value = format!("{character}120{character}");
            assert_eq!(parse_integer(&value), None);
            assert_eq!(parse_integer(strip(&value)), Some(120));
            assert_eq!(strip(&format!("{character}true{character}")), "true");
        }
        assert_eq!(strip("\u{200b}true\u{200b}"), "\u{200b}true\u{200b}");
    }
}
