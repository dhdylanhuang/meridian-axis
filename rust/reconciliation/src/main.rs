use axis_reconciliation::{reconcile, Request, MAX_INPUT_BYTES};
use std::io::{self, Read};

fn main() {
    let result = (|| {
        let mut input = Vec::new();
        io::stdin()
            .take(MAX_INPUT_BYTES + 1)
            .read_to_end(&mut input)
            .map_err(|_| "input_read_failed")?;
        if input.len() as u64 > MAX_INPUT_BYTES {
            return Err("input_size_limit");
        }
        let request: Request = serde_json::from_slice(&input).map_err(|_| "request_invalid")?;
        let report = reconcile(request).map_err(|error| error.0)?;
        serde_json::to_writer(io::stdout().lock(), &report).map_err(|_| "output_failed")
    })();
    if let Err(code) = result {
        eprintln!("{code}");
        std::process::exit(2);
    }
}
