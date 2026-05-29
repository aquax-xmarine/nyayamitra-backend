import pdfplumber

with pdfplumber.open("082-wh-0086_N1.pdf") as pdf:
    page = pdf.pages[0]
    
    # Check layers
    char_count = len(page.chars)
    image_count = len(page.images)
    
    # Check fonts
    fonts = set()
    for char in page.chars:
        if 'fontname' in char:
            fonts.add(char['fontname'])
    
    print(f"Char count: {char_count}")
    print(f"Image count: {image_count}")
    print(f"Fonts used: {fonts}")
    
    # Check image coverage
    for img in page.images:
        coverage = (img['width'] * img['height']) / \
                   (page.width * page.height)
        print(f"Image coverage: {coverage:.0%}")