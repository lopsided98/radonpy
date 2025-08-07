{
  lib,
  fetchFromGitHub,
  buildPythonApplication,
  setuptools,
  aioinflux,
  bleak,
  black,
  flake8,
  mypy,
}:

buildPythonApplication {
  pname = "radonpy";
  version = "0.2.4";

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
