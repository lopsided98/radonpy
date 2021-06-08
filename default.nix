{ lib, fetchFromGitHub, buildPythonApplication, black, flake8, bleak
, aioinflux }:

buildPythonApplication {
  pname = "radonpy";
  version = "0.1.0";

  src = ./.;

  nativeBuildInputs = [ black flake8 ];
  propagatedBuildInputs = [ bleak aioinflux ];

  preCheck = ''
    black --check .
    flake8
  '';

  meta = with lib; {
    description = "Tools to communicate with the RadonEye RD200 radon detector";
    homepage = "https://github.com/lopsided98/radonpy";
    license = licenses.asl20;
    maintainers = with maintainers; [ lopsided98 ];
    platforms = platforms.all;
  };
}
