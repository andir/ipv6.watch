with import <nixpkgs> {};
stdenv.mkDerivation {
  name = "buildenv";
  buildInputs = with python3Packages; [
    aiodns
    aiohttp
    click
    jinja2
    jsonschema
    pyyaml
  ];
}
