import argparse
import logging
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError


logging.basicConfig(level=logging.INFO)


def hex2rgb(hex):
    assert len(hex) == 6

    return [int(hex[o : o + 2], 16) for o in [0, 2, 4]]


def is_hex(value):
    return re.match("^[A-Fa-f0-9]{6}$", value)


def parse_margin(margin):
    a, b, c, d, *ignore = [abs(int(n)) for n in margin.split(",")] + [None] * 4

    if d:
        return [a, b, c, d]
    elif c:
        return [a, b, c, b]
    elif b:
        return [a, b, a, b]
    elif a:
        return [a, a, a, a]
    else:
        return [0, 0, 0, 0]


def parse_args(args):
    parser = argparse.ArgumentParser(
        conflict_handler="resolve",
        description="Removes extra borders to correctly resize the logo to fit the specified bounding-box.",
    )

    parser.add_argument("images", nargs="+", metavar="<IMAGE(S)>", help="")
    parser.add_argument("-h", "--height", type=int, required=True, help="")
    parser.add_argument("-w", "--width", type=int, required=True, help="")
    parser.add_argument("-m", "--margin", default="0", help="")
    parser.add_argument("-b", "--background", help="")
    parser.add_argument("-o", "--output", default="cropped")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")

    foreground = parser.add_mutually_exclusive_group()
    foreground.add_argument("-g", "--greyscale", action="store_true", help="")
    foreground.add_argument("-c", "--color", help="")

    args = parser.parse_args()

    if args.color:
        if is_hex(args.color):
            args.color = hex2rgb(args.color)
        else:
            raise argparse.ArgumentTypeError(
                "Please specify --color as 6-symbol HEX value e.g. --color ffab03"
            )

    if args.background:
        if is_hex(args.background):
            args.background = hex2rgb(args.background)
        else:
            raise argparse.ArgumentTypeError(
                "Please specify --background as 6-symbol HEX value e.g. --background ffab03"
            )

    args.width = abs(args.width)
    args.height = abs(args.height)

    args.margin = parse_margin(args.margin)

    assert (
        args.width > args.margin[1] + args.margin[3]
    ), "Width should be greater than sum of margins"

    assert (
        args.height > args.margin[0] + args.margin[2]
    ), "Height should be greater than sum of margins"

    return args


def resize_to_fit_bounding_box(img, bb_width, bb_height):
    img_width, img_height = img.size

    bb_ratio = bb_width / bb_height
    img_ratio = img_width / img_height

    if bb_ratio > img_ratio:
        new_img_width = img_width / img_height * bb_height
        new_img_height = bb_height
    else:
        new_img_width = bb_width
        new_img_height = img_height / img_width * bb_width

    new_img_width = int(new_img_width)
    new_img_height = int(new_img_height)

    return (
        img.resize((new_img_width, new_img_height), Image.LANCZOS),
        new_img_width,
        new_img_height,
    )


def main(args=None):
    if not args:
        args = sys.argv[1:]

    args = parse_args(args)

    if args.debug:
        print(args)

    Path(args.output).mkdir(mode=0o777, parents=True, exist_ok=True)

    for path in args.images:
        image = None

        try:
            image = Image.open(path).convert("RGBA")

            if args.verbose:
                logging.info(f" Image `{path}` correctly opened")
        except FileNotFoundError:
            logging.warning(f" File `{path}` not found")
        except UnidentifiedImageError:
            # TODO: try to open as SVG and convert to raster image
            logging.warning(f" File `{path}` can't be opened")

        if not image:
            continue

        if image.getpixel((3, 3))[3] == 0:
            bounding_box = image.getbbox()
        else:
            posterized = ImageOps.posterize(image.convert("RGB"), 1)

            background = Image.new(
                "RGBA", image.size, posterized.getpixel((3, 3))
            ).convert("RGB")

            bounding_box = ImageChops.difference(posterized, background).getbbox()

        cropped = image.crop(bounding_box)

        top, right, bottom, left = args.margin

        resized, rw, rh = resize_to_fit_bounding_box(
            cropped, args.width - left - right, args.height - top - bottom
        )

        background_color = image.getpixel((3, 3))

        if args.background:
            background_color = tuple(args.background + [255])

        if args.color:
            r, g, b, a = resized.split()

            r = r.point(lambda v: args.color[0])
            g = g.point(lambda v: args.color[1])
            b = b.point(lambda v: args.color[2])

            resized = Image.merge("RGBA", (r, g, b, a))

        logo_layer = Image.new("RGBA", (args.width, args.height), (128, 128, 128, 0))
        logo_layer.paste(
            resized,
            (
                left + (args.width - left - right - rw) // 2,
                top + (args.height - top - bottom - rh) // 2,
            ),
            resized,
        )
        background = Image.new("RGBA", (args.width, args.height), background_color)

        final = Image.alpha_composite(background, logo_layer)

        if args.greyscale:
            final = final.convert("LA")

        final.save(f"./{args.output}/{Path(path).stem}.png")

if __name__ == '__main__':
    main()
