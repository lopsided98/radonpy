{
  description = "Tools to communicate with the RadonEye RD200 radon detector";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, }:
    with flake-utils.lib;
    eachSystem allSystems
      (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          defaultPackage = pkgs.python3Packages.callPackage ./. { };

          defaultApp = {
            type = "app";
            program = "${self.defaultPackage.${system}}/bin/radonpy";
          };

          devShell = self.defaultPackage.${system};
        }) //
    eachSystem [ "x86_64-linux" ] (system: {
      hydraJobs.build = self.defaultPackage.${system};
    }) // {
      overlay = import ./pkgs;
      nixosModule = import ./module.nix;
    };
}
