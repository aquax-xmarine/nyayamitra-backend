import pdfplumber

with pdfplumber.open("0009-01_E1.pdf") as pdf:
    page = pdf.pages[0]
    
    # Check text layer
    chars = page.chars
    print(f"Text layer chars: {len(chars)}")
    
    # Check image layer
    images = page.images
    print(f"Image layer count: {len(images)}")
    
    for img in images:
        print(f"Image size: {img['width']} x {img['height']}")
        print(f"Page size:  {page.width} x {page.height}")
        coverage = (img['width'] * img['height']) / \
                   (page.width * page.height)
        print(f"Coverage:   {coverage:.0%}")