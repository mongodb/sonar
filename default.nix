{ pkgs ? import <nixpkgs> {} }:
  pkgs.mkShell {
    buildInputs = [
      pkgs.python37
    ];

    shellHook = ''
      VIRTUAL_ENV_LOCATION=$HOME/.virtualenvs/sonar
      [ -d $VIRTUAL_ENV_LOCATION ] || (mkdir -p $HOME/.virtualenvs && python -m venv $VIRTUAL_ENV_LOCATION)
      source $VIRTUAL_ENV_LOCATION/bin/activate

      # Updates pip
      python -m pip install --upgrade pip
      # Install/update requirements
      python -m pip install -r requirements.txt --use-feature=2020-resolver &> /dev/null
    '';
}
