import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def probe():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await ctx.new_page()
        await page.goto(
            'https://help.dayforce.com/r/documents/Dayforce-RESTful-Web-Services-Developer-Guide/RESTful-Retrieve-Department-Data',
            timeout=30000, wait_until='networkidle'
        )
        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')

        # Remove scripts and styles
        for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()

        # Check headings
        print("=== HEADINGS ===")
        for h in soup.find_all(['h1','h2','h3','h4']):
            print(f"  <{h.name}>: {h.get_text(strip=True)[:100]}")

        # Check paragraphs
        print("\n=== PARAGRAPHS (first 5) ===")
        for p in soup.find_all('p')[:5]:
            text = p.get_text(strip=True)
            if text:
                print(f"  {text[:120]}")

        # Check pre/code blocks
        print("\n=== CODE/PRE BLOCKS (first 3) ===")
        for pre in soup.find_all(['pre','code'])[:3]:
            text = pre.get_text(strip=True)
            if text:
                print(f"  {text[:150]}")

        # Check tables
        print("\n=== TABLES ===")
        for tbl in soup.find_all('table')[:2]:
            print(f"  Table rows: {len(tbl.find_all('tr'))}")
            for tr in tbl.find_all('tr')[:3]:
                print(f"    {tr.get_text(' | ', strip=True)[:100]}")

        # Main content area
        print("\n=== MAIN CONTENT SNIPPET ===")
        main = soup.find('main') or soup.find('article') or soup.find(class_=lambda c: c and 'content' in c.lower())
        if main:
            print(main.get_text(' ', strip=True)[:500])
        else:
            print("No main/article found")
            body = soup.find('body')
            if body:
                print(body.get_text(' ', strip=True)[:500])

        await browser.close()

asyncio.run(probe())
