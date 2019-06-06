with import <nixpkgs> {};
stdenv.mkDerivation {
  name = "buildenv";
  buildInputs = with python3Packages; [
    jinja2
    pyyaml
    jsonschema
    aiodns
    htmlmin
  ];
}
