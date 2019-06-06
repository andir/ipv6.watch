# [ipv6.watch](https://ipv6.watch)

[![https://img.shields.io/travis/andir/ipv6.watch.svg](https://travis-ci.org/andir/ipv6.watch)]

Although IPv6 has been around since 1998, some big parts of the internet are IPv4 only. Since World IPv6 Launch day on June 6 2012 the global IPv6 traffic has grown more than 500%. However, the adoption at major websites is still bad even though they should have the money, time and people to provide IPv6 connectivity.

This repository contains code to check some website domains for AAAA records using multipe public available DNS resolvers and generate a static website containing the results.

![](https://raw.githubusercontent.com/andir/ipv6.watch/master/misc/World_IPv6_launch_banner_512.png)

## Contributing + Dev info

### Missing websites or website infos

You can report missing websites or domains by opening an issue. If you want to provide them yourself have a look at the developer documentation down below.

## Documentation for developers

### Used DNS resolvers

The used DNS resolvers are configured in `config.yml`. Each key under `nameservers` represents a different DNS resolver provider. Each provider contains a list with the respective resolver IPs. Some of them (mostly the primary IPs) are commented out. There is no real advantage checking against a primary and a secondary resolver. Instead the main focus relies on one IPv4 and one IPv6 resolver.

### Categories

The categories are also stored in `config.yml`. The variable `categories` contains a list with the predefined category. If you want to create a new one make sure you add at least two or three targets.   
Make sure you never delete `Uncategorized`. This will break the python code!

### Targets

Each website is called a target. All targets are configured in `config.yml`. Each websites display name is the key of the `targets` dictionary.   
Each target must at least contain the following keys:

- `href`: Single value containing a link to the websites front page
- `hosts`: A list containing at least one domain to check for AAAA records. Only include domains where website ressources are gathered from. Skip CND domains.

The following keys are optional:

- `icon`: Link to an FontAwesome glyph or a picture. See section `Adding icons` for more details
- `twitter`: If the website has one or more twitter handles you can add them here. Don't forget to add quotes! Multiple twitter handles are seperated by a whitespace.
- `categories`: Contains a list with category names. This is used to render a host into the respective categories. A target can be part of multiple categories. If this key is missing the target will be automatically grouped into the category `Uncategorized`

### Adding icons

Adding icons helps to quickly identify a target.

#### By using FontAwesome

If you find an icon provided by [FontAwesome](https://fontawesome.com/icons?d=gallery&s=brands) you can add it by setting the `icon` key of a target to `fa-iconname`. The page renderer will recognize the `fa`-Prefix and will create a glyph.

#### By providing an image

If you can provide an image for a target you can add it to `dist/images/`. Afterwards set the `icon` key to the filename.   
Some websites provide their official logos and their guidelins of how to use them. You can find them by using your favorite search engine. Some search terms to find them:

- `website logo guidelines`
- `website logo press center`
- `website logo press media`

If you find no good source try to contact the website owner (for example on Twitter) and ask them if they have guidelines and if you are allowed to use their logo.   
Please add the image source near the `icon` key and (if available) a link to the licence, guideline and/or permission. Please don't manipulate images in any way if it's forbidden.

Before you add the file to the repository make sure you optimize the file size to save bandwidth and speed up the page.   
Here is a list of tools you can use:

- `optipng` for PNG files
- `jpegoptim` for JPG/JPEG files
- [scour](https://github.com/scour-project/scour) for SVG files

Most images can be reduced by more than 80% in file size.

### Formatting config.yml

YAML files are sometimes hard to format properly. You can use `yamlfmt` to format `config.yml` it properly before checking it in: `yamlfmt -w config.yml`

### Minifying HTML

When you generate the static page it's very huge. It consumes round about 1.3 MByte disk space and consists of many blank spaces which are good for a human developer working and debugging the generated HTML. A computer doesn't need them and only wastes ressources on it. That's why minifiers were developed. They remove unnecessary spaces, newlines etc to save up space.   
Minifying the HTML reduces the HTML to round about 546 KByte. That's a reduction of 59%. The benefits are simple: The page loads faster and less CPU is needed for rendering it in the browser. On the other side debugging a minified HTML isn't fun.

By default the HTML is not minified. If you pass `-m` or `--minify` to the generator script the output will be minified. Use the normal version for developing and the minified version for production.
