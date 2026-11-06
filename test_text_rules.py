import unittest

from text_rules import validate_post, remove_source_footer


class RTLTests(unittest.TestCase):
    def test_duplicate_source_footer_removed_but_prose_preserved(self):
        url = 'https://example.com/news'
        body = 'این خبر است.\n\nمنبع: [نام](https://example.com/news)'
        self.assertEqual(remove_source_footer(body, url), 'این خبر است.')
        self.assertEqual(remove_source_footer('این لینک در متن است: '+url, url), 'این لینک در متن است: '+url)
        self.assertEqual(remove_source_footer('این خبر است.\n\nمنبع: https://other.com', url), 'این خبر است.\n\nمنبع: https://other.com')

    def test_any_nonzero_number_of_persian_paragraphs(self):
        validate_post('این یک پاراگرافه.')
        validate_post('\n\n'.join(['این یک پاراگرافه.'] * 5))
        with self.assertRaises(ValueError):
            validate_post('  ')

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
