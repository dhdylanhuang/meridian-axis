//! Host boundary only; all financial rules stay in the existing pure core.
use crate::{reconcile, Request};
use wasm_bindgen::prelude::*;

const MAX_WASM_BYTES: usize = 512 * 1024;
const MAX_WASM_OBSERVATIONS: usize = 1_024;

#[wasm_bindgen]
pub fn reconcile_cash_json(input: &str) -> Result<String, JsValue> {
    if input.len() > MAX_WASM_BYTES {
        return Err(JsValue::from_str("input_size_limit"));
    }
    let request: Request =
        serde_json::from_str(input).map_err(|_| JsValue::from_str("request_invalid"))?;
    if request.observations.len() > MAX_WASM_OBSERVATIONS {
        return Err(JsValue::from_str("wasm_observation_limit"));
    }
    let report = reconcile(request).map_err(|error| JsValue::from_str(error.0))?;
    serde_json::to_string(&report).map_err(|_| JsValue::from_str("output_failed"))
}

#[wasm_bindgen]
pub fn portfolio_exposures_json(input: &str) -> Result<String, JsValue> {
    if input.len() > MAX_WASM_BYTES {
        return Err(JsValue::from_str("input_size_limit"));
    }
    let request = serde_json::from_str(input).map_err(|_| JsValue::from_str("request_invalid"))?;
    let report =
        crate::exposures::calculate(request).map_err(|error| JsValue::from_str(error.0))?;
    serde_json::to_string(&report).map_err(|_| JsValue::from_str("output_failed"))
}

#[wasm_bindgen]
pub fn observed_performance_json(input: &str) -> Result<String, JsValue> {
    crate::performance::calculate_json(input).map_err(|error| JsValue::from_str(error.0))
}

#[wasm_bindgen]
pub fn portfolio_changes_json(input: &str) -> Result<String, JsValue> {
    crate::changes::calculate_json(input).map_err(|error| JsValue::from_str(error.0))
}

#[wasm_bindgen]
pub fn portfolio_projection_json(input: &str) -> Result<String, JsValue> {
    crate::projections::calculate_json(input).map_err(|error| JsValue::from_str(error.0))
}

#[wasm_bindgen]
pub fn portfolio_stress_json(input: &str) -> Result<String, JsValue> {
    crate::stress::calculate_json(input).map_err(|error| JsValue::from_str(error.0))
}

#[wasm_bindgen]
pub fn portfolio_sector_rollup_json(input: &str) -> Result<String, JsValue> {
    crate::exposures::sector_rollup_json(input).map_err(|error| JsValue::from_str(error.0))
}

#[wasm_bindgen]
pub fn portfolio_meridian_json(input: &str) -> Result<String, JsValue> {
    crate::meridian::calculate_json(input).map_err(|error| JsValue::from_str(error.0))
}
