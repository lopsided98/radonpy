{ lib, fetchFromGitHub, buildPythonApplication, black, flake8, mypy, aioinflux
, bleak }:

buildPythonApplication rec {
  pname = "radonpy";
  version = "0.2.2";

  src = ./.;

  nativeBuildInputs = [ black flake8 mypy ];
  propagatedBuildInputs = [ aioinflux bleak ];

  postBuild = ''
    black --check .
    flake8
    mypy radonpy
  '';

  # No tests
  doCheck = false;

  meta = with lib; {
    description = "Tools to communicate with the RadonEye RD200 radon detector";
    homepage = "https://github.com/lopsided98/radonpy";
    license = licenses.asl20;
    maintainers = with maintainers; [ lopsided98 ];
    platforms = platforms.all;
  };
}
