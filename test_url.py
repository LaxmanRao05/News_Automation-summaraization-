
from google import resolve_article_url

test_url = input("Paste a Google News article URL: ").strip()

result = resolve_article_url(test_url)

print("\nResolved URL:")
print(result)
