{
  lib,
  callPackage,
  fetchFromGitHub,
  buildPythonApplication,
  setuptools,
  bleak,
  black,
  flake8,
  mypy,
}:
let
  aioinflux = callPackage (
    {
      lib,
      buildPythonPackage,
      fetchPypi,
      aiohttp,
      ciso8601,
      setuptools,
      pandas,
    }:

    buildPythonPackage rec {
      pname = "aioinflux";
      version = "0.9.0";
      pyproject = true;

      src = fetchPypi {
        inherit pname version;
        hash = "sha256-cg0FapBprDaI+Ds1eGsjTIkK+3yaN560IeU3nh6rxcs=";
      };

      build-system = [ setuptools ];

      dependencies = [
        aiohttp
        ciso8601
        pandas
      ];

      # Tests require InfluxDB server
      doCheck = false;

      pythonImportsCheck = [ "aioinflux" ];

      meta = {
        description = "Asynchronous Python client for InfluxDB";
        homepage = "https://github.com/gusutabopb/aioinflux";
        changelog = "https://github.com/gusutabopb/aioinflux/releases/tag/v${version}";
        license = lib.licenses.mit;
        maintainers = with lib.maintainers; [
          lopsided98
        ];
      };
    }
  ) { };
in
buildPythonApplication {
  pname = "radonpy";
  version = "0.2.5";

  src = ./.;

  pyproject = true;
  build-system = [ setuptools ];
  dependencies = [
    aioinflux
    bleak
  ];
  nativeCheckInputs = [
    black
    flake8
    mypy
  ];

  preCheck = ''
    black --check .
    flake8
    mypy radonpy
  '';

  pythonImportsCheck = [ "radonpy" ];

  meta = with lib; {
    description = "Tools to communicate with the RadonEye RD200 radon detector";
    homepage = "https://github.com/lopsided98/radonpy";
    license = licenses.asl20;
    maintainers = with maintainers; [ lopsided98 ];
    platforms = platforms.all;
  };
}
