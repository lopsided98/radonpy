{
  config,
  lib,
  pkgs,
  ...
}:

with lib;

let
  cfg = config.services.radonpy;
in
{
  options.services.radonpy = {
    enable = mkEnableOption "RadonEye data collection to InfluxDB";

    adapter = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "hci1";
      description = ''
        Name or address of Bluetooth adapter. If null, the adapter is chosen
        automatically.
      '';
    };

    address = mkOption {
      type = types.nullOr types.str;
      default = null;
      example = "C4:AC:34:45:E4:2A";
      description = ''
        Connect to device with this Bluetooth address. If null, the first RD200
        device found is used.
      '';
    };

    influxdb = {
      excludeFields = mkOption {
        type = types.listOf (
          types.enum [
            "current_value"
            "day_value"
            "month_value"
            "pulse_count"
            "pulse_count_10_min"
          ]
        );
        default = [ ];
        description = ''
          List of fields to exclude from the InfluxDB measurement
        '';
      };

      url = mkOption {
        type = types.str;
        description = "InfluxDB URL";
      };

      database = mkOption {
        type = types.str;
        default = "radonpy";
        description = "InfluxDB database";
      };

      username = mkOption {
        type = types.str;
        default = "radonpy";
        description = "InfluxDB username";
      };

      password = mkOption {
        type = types.str;
        default = "";
        description = ''
          InfluxDB password. Will be stored in plain text in the Nix store.
        '';
      };

      tlsCertificate = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "X.509 certificate for client authentication";
      };

      tlsKey = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "X.509 private key for client authentication";
      };
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion =
          cfg.influxdb.tlsCertificate != null
          -> cfg.influxdb.tlsKey != null && cfg.influxdb.tlsKey != null
          -> cfg.influxdb.tlsCertificate != null;
        message = ''
          services.radonpy.influxdb.tlsCertificate and
          services.radonpy.influxdb.tlsKey must both be provided to enable
          client certificate authentication.
        '';
      }
    ];

    users = {
      users.radonpy = {
        isSystemUser = true;
        group = "radonpy";
      };
      groups.radonpy = { };
    };

    hardware.bluetooth.enable = true;

    services.dbus.packages = singleton (
      pkgs.writeTextFile {
        name = "dbus-radonpy-bluetooth.conf";
        destination = "/etc/dbus-1/system.d/radonpy-bluetooth.conf";
        text = ''
          <!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
           "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
          <busconfig>
            <policy user="radonpy">
              <allow send_destination="org.bluez"/>
            </policy>
          </busconfig>
        '';
      }
    );

    systemd.services.radonpy =
      let
        radonpy = pkgs.python3Packages.callPackage ./. { };
      in
      {
        wantedBy = [ "multi-user.target" ];
        after = [ "bluetooth.target" ];
        serviceConfig = {
          Type = "exec";
          User = "radonpy";
          Group = "radonpy";
          Restart = "always";
          RestartSec = 5;
          ExecStart = lib.escapeShellArgs (
            [
              "${radonpy}/bin/radonpy"
            ]
            ++ lib.optionals (cfg.adapter != null) [
              "--adapter"
              cfg.adapter
            ]
            ++ lib.optionals (cfg.address != null) [
              "--address"
              cfg.address
            ]
            ++ [
              "influxdb"
              "--url"
              cfg.influxdb.url
              "--database"
              cfg.influxdb.database
              "--username"
              cfg.influxdb.username
              "--password"
              cfg.influxdb.password
            ]
            ++ lib.optionals (cfg.influxdb.tlsCertificate != null) [
              "--tls-certificate"
              "${cfg.influxdb.tlsCertificate}"
              "--tls-key"
              "${cfg.influxdb.tlsKey}"
            ]
            ++ lib.concatMap (f: [
              "--exclude-field"
              f
            ]) cfg.influxdb.excludeFields
          );
        };
        unitConfig = {
          StartLimitBurst = 5;
          StartLimitIntervalSec = 150;
        };
      };
  };
}
