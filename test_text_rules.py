import unittest

from text_rules import validate_post


class RTLTests(unittest.TestCase):
    def test_persian_start_with_english_name_after_it(self):
        validate_post('شرکت Airbnb خبر داده.\n\nاین یک نمونه‌ست.\n\nحالا می‌شه بررسیش کرد.')

    def test_rejects_bad_start_in_any_paragraph(self):
        for initial in ('Airbnb', '۲۰۲۷', '2027', '🤖', '«گوگل', '(گوگل'):
            for index in range(3):
                paragraphs = ['این یک نمونه‌ست.'] * 3
                paragraphs[index] = initial + ' خبر داده.'
                with self.subTest(initial=initial, paragraph=index):
                    with self.assertRaises(ValueError):
                        validate_post('\n\n'.join(paragraphs))
