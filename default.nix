{ lib, fetchFromGitHub, buildPythonApplication, python, aioinflux, bleak, black
, flake8, mypy }:

buildPythonApplication rec {
  pname = "radonpy";
  version = "0.2.1";

  src = ./.;

  propagatedBuildInputs = [ aioinflux bleak ];

  checkInputs = [ black flake8 mypy ];

  preCheck = ''
    black --check .
    flake8
    mypy radonpy
  '';

  meta = with lib; {
    description = "Tools to communicate with the RadonEye RD200 radon detector";
    homepage = "https://github.com/lopsided98/radonpy";
    license = licenses.asl20;
    maintainers = with maintainers; [ lopsided98 ];
    platforms = platforms.all;
  };
}
