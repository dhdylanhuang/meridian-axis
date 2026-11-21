use axis_reconciliation::risk_sessions::audit_with_funding;
use std::fs::File;
use std::io::{self, Read};

fn check() -> Result<(), &'static str> {
    let mut args = std::env::args().skip(1);
    const USAGE: &str = "usage: qualify_daily UTC_AS_OF [FUNDING_JSON] < reviewed.json";
    let as_of = args.next().ok_or(USAGE)?;
    let funding_path = args.next();
    if args.next().is_some() {
        return Err(USAGE);
    }
    let funding = funding_path
        .map(|path| {
            let mut bytes = Vec::new();
            File::open(path)
                .and_then(|file| file.take(128 * 1024 + 1).read_to_end(&mut bytes))
                .map_err(|_| "funding_read_failed")?;
            Ok(bytes)
        })
        .transpose()?;
    let mut input = Vec::new();
    io::stdin()
        .take(512 * 1024 + 1)
        .read_to_end(&mut input)
        .map_err(|_| "input_read_failed")?;
    let summary = audit_with_funding(&input, &as_of, funding.as_deref()).map_err(|err| err.0)?;
    println!("{summary}");
    Ok(())
}

fn main() {
    if let Err(code) = check() {
        eprintln!("{code}");
        std::process::exit(2);
    }
}
