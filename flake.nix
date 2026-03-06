{
  description = "ShuMao Development Flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs, ...} @ inputs: 
  let
    # Change me!
    system = "x86_64-linux";
    pkgs = import nixpkgs { inherit system; };
  in {
    devShells.x86_64-linux.default = pkgs.mkShell {
      packages = [
        (pkgs.python3.withPackages(p: with p; [
          flask
          stanza
        ]))
      ];
      
      env.LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
        pkgs.stdenv.cc.cc.lib
      ];

    };


    apps.${system}.default = let
      serv = pkgs.writeShellApplication {
        # Our shell script name is serve
        # so it is available at $out/bin/serve
        name = "serve-shumao";
        # Caddy is a web server with a convenient CLI interface
        runtimeInputs = [pkgs.caddy];
        text = ''
          ( 
            PORT=8080
            HOST="0.0.0.0"
            if [ "$#" -eq 2 ]; then
              HOST=$1
              PORT=$2
            fi
            flask run --host="$HOST" --port="$PORT"
          )
        '';
      };
    in {
      type = "app";
      # Using a derivation in here gets replaced
      # with the path to the built output
      program = "${serv}/bin/serve-shumao";
    };
  

  };
}
