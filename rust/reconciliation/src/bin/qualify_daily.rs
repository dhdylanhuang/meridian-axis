use axis_reconciliation::risk_sessions::audit_json;
use std::io::{self, Read};

fn check() -> Result<(), &'static str> {
    let mut args = std::env::args().skip(1);
    let as_of = args
        .next()
        .ok_or("usage: qualify_daily UTC_AS_OF < reviewed.json")?;
    if args.next().is_some() {
        return Err("usage: qualify_daily UTC_AS_OF < reviewed.json");
    }
    let mut input = Vec::new();
    io::stdin()
        .take(512 * 1024 + 1)
        .read_to_end(&mut input)
        .map_err(|_| "input_read_failed")?;
    let summary = audit_json(&input, &as_of).map_err(|err| err.0)?;
    println!("{summary}");
    Ok(())
}

fn main() {
    if let Err(code) = check() {
        eprintln!("{code}");
        std::process::exit(2);
    }
}
