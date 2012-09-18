Usage: poclbm.py [OPTION]... SERVER[#tag]...
SERVER is one or more [http[s]|stratum://]user:pass@host:port          (required)
[#tag] is a per SERVER user friendly name displayed in stats (optional)

Options:
  --version             show program's version number and exit
  -h, --help            show this help message and exit
  --verbose             verbose output, suitable for redirection to log file
  -q, --quiet           suppress all output except hash rate display
  --proxy=PROXY         specify as
                        [[socks4|socks5|http://]user:pass@]host:port (default
                        proto is socks5)

  Miner Options:
    -r RATE, --rate=RATE
                        hash rate display interval in seconds, default=1 (60
                        with --verbose)
    -e ESTIMATE, --estimate=ESTIMATE
                        estimated rate time window in seconds, default 900 (15
                        minutes)
    -a ASKRATE, --askrate=ASKRATE
                        how many seconds between getwork requests, default 5,
                        max 10
    -t TOLERANCE, --tolerance=TOLERANCE
                        use fallback pool only after N consecutive connection
                        errors, default 2
    -b FAILBACK, --failback=FAILBACK
                        attempt to fail back to the primary pool after N
                        seconds, default 60
    --cutoff_temp=CUTOFF_TEMP
                        (requires github.com/mjmvisser/adl3) temperature at
                        which to skip kernel execution, in C, default=95
    --cutoff_interval=CUTOFF_INTERVAL
                        (requires adl3) how long to not execute calculations
                        if CUTOFF_TEMP is reached, in seconds, default=0.01
    --no-server-failbacks
                        disable using failback hosts provided by server

  Kernel Options:
    -p PLATFORM, --platform=PLATFORM
                        use platform by id
    -d DEVICE, --device=DEVICE
                        use device by id, by default asks for device
    -w WORKSIZE, --worksize=WORKSIZE
                        work group size, default is maximum returned by opencl
    -f FRAMES, --frames=FRAMES
                        will try to bring single kernel execution to 1/frames
                        seconds, default=30, increase this for less desktop
                        lag
    -s FRAMESLEEP, --sleep=FRAMESLEEP
                        sleep per frame in seconds, default 0
    -v, --vectors       use vectors