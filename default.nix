{ lib, fetchFromGitHub, buildPythonApplication, python, aioinflux, bleak, black
, flake8, mypy }:

buildPythonApplication rec {
  pname = "radonpy";
  version = "0.1.0";

  src = ./.;

  propagatedBuildInputs = [ aioinflux bleak ];

  checkInputs = [ black flake8 mypy ];

  preCheck = let
    # mypy only supports packages in the interpreter site-packages directory
    # https://github.com/python/mypy/issues/5701
    env = python.withPackages (p: propagatedBuildInputs);
  in ''
    black --check .
    flake8
    mypy --python-executable '${env.interpreter}' radonpy
  '';

  meta = with lib; {
    description = "Tools to communicate with the RadonEye RD200 radon detector";
    homepage = "https://github.com/lopsided98/radonpy";
    license = licenses.asl20;
    maintainers = with maintainers; [ lopsided98 ];
    platforms = platforms.all;
  };
}
