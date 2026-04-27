# MMM NixOS Module
# Add to your configuration.nix or imports:
#   imports = [ /path/to/nixos-module.nix ];
#
# Then configure:
#   services.mmm = {
#     enable = true;
#     ollamaHost = "http://localhost:11435";
#     proxyPort = 11434;
#   };

{ config, pkgs, lib, ... }:

let
  cfg = config.services.mmm;
  pythonWithPackages = pkgs.python3.withPackages (ps: with ps; [
    fastapi
    uvicorn
    httpx
  ]);
in {
  options.services.mmm = {
    enable = lib.mkEnableOption "MMM — Make Modelfiles Matter Ollama proxy";

    ollamaHost = lib.mkOption {
      type    = lib.types.str;
      default = "http://localhost:11434";
      description = "URL of the Ollama instance to proxy to";
    };

    proxyPort = lib.mkOption {
      type    = lib.types.port;
      default = 11435;
      description = "Port the MMM proxy listens on";
    };

    dataDir = lib.mkOption {
      type    = lib.types.path;
      default = "/opt/mmm";
      description = "Directory containing proxy.py and characters.json";
    };

    user = lib.mkOption {
      type    = lib.types.str;
      default = "mmm";
      description = "User to run the proxy as";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.mmm = {
      description = "MMM — Make Modelfiles Matter";
      after       = [ "network.target" ];
      wantedBy    = [ "multi-user.target" ];

      environment = {
        OLLAMA_HOST = cfg.ollamaHost;
        PROXY_PORT  = toString cfg.proxyPort;
      };

      serviceConfig = {
        Type             = "exec";
        User             = cfg.user;
        WorkingDirectory = cfg.dataDir;
        ExecStart        = "${pythonWithPackages}/bin/python3 ${cfg.dataDir}/proxy.py";
        Restart          = "on-failure";
        RestartSec       = "5s";
      };
    };

    users.users = lib.mkIf (cfg.user == "mmm") {
      mmm = {
        isSystemUser = true;
        group        = "mmm";
        description  = "MMM proxy service user";
      };
    };

    users.groups = lib.mkIf (cfg.user == "mmm") {
      mmm = {};
    };
  };
}
