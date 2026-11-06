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

    def test_rejects_english_prose_with_persian_prefix(self):
        with self.assertRaises(ValueError):
            validate_post('در توضیح این خبر، This is an English article copied directly from a feed without translation.')
        with self.assertRaises(ValueError):
            validate_post('این مقدمه فارسیه.\n\nدر توضیح این خبر، The model can run a game and was released this week.')

    def test_allows_persian_prose_with_names_and_links(self):
        validate_post('شرکت OpenAI مدل GPT-6 رو معرفی کرده و دربارهٔ قابلیت‌هاش توضیح داده.')
        validate_post('این خبر دربارهٔ یک پروژهٔ تازه است: https://example.com/a-long-english-path')

    def test_rejects_bad_start_in_any_paragraph(self):
        for initial in ('Airbnb', '۲۰۲۷', '2027', '🤖', '«گوگل', '(گوگل'):
            for index in range(3):
                paragraphs = ['این یک نمونه‌ست.'] * 3
                paragraphs[index] = initial + ' خبر داده.'
                with self.subTest(initial=initial, paragraph=index):
                    with self.assertRaises(ValueError):
                        validate_post('\n\n'.join(paragraphs))
