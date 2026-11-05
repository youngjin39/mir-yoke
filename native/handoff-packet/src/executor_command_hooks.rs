//! Command-owned hook routing. Python object handles never cross native stdio.
use crate::{
    executor_hooks::HookSession,
    local_bridge::{BridgeConfig, BridgeError, LocalBridge},
};
use serde_json::{Value, json};
use std::path::Path;

pub trait HookClient {
    fn call(&mut self, name: &str, args: Vec<Value>, options: Value) -> Result<Value, BridgeError>;
}
impl HookClient for LocalBridge {
    fn call(&mut self, name: &str, args: Vec<Value>, options: Value) -> Result<Value, BridgeError> {
        LocalBridge::call(self, name, args, options)
    }
}
#[derive(Clone, Copy, Debug)]
pub enum TeardownOutcome {
    Clean,
    Unclean,
    Uncertain,
}
impl TeardownOutcome {
    fn as_str(self) -> &'static str {
        match self {
            Self::Clean => "clean",
            Self::Unclean => "unclean",
            Self::Uncertain => "uncertain",
        }
    }
}
#[derive(Debug)]
pub struct CommandHooks {
    pub(crate) python: Option<LocalBridge>,
    native: Option<HookSession>,
    hello: Value,
    context: Value,
    token: Option<String>,
    outcome: TeardownOutcome,
    brief_profile: Option<crate::executor_brief_profile::BriefProfile>,
    job_identity: Option<crate::executor_job_identity::JobIdentity>,
}
impl CommandHooks {
    pub fn start_in(config: BridgeConfig, cwd: &Path) -> Result<Option<Self>, BridgeError> {
        let policy = crate::executor_admission::native_policy(&config.target_root)
            .map_err(BridgeError::Configuration)?;
        // Start the bridge first: its hello can reveal computed duplicate exports.
        let python = LocalBridge::start_in(
            BridgeConfig {
                interpreter: config.interpreter.clone(),
                target_root: config.target_root.clone(),
                bridge_script: config.bridge_script.clone(),
                environment: config.environment.clone(),
                timeout: config.timeout,
            },
            cwd,
        )?;
        let native = policy
            .as_ref()
            .and_then(|p| p.hooks.as_ref())
            .map(|hooks| {
                HookSession::start_in_environment(
                    &config.target_root,
                    cwd,
                    hooks,
                    &config.environment,
                    config.timeout,
                )
            })
            .transpose()?;
        let brief_profile = policy.as_ref().and_then(|p| p.brief_profile.clone());
        let job_identity = policy
            .as_ref()
            .and_then(|p| p.job_identity.clone())
            .filter(|identity| identity.enabled());
        if python.is_none() && native.is_none() && brief_profile.is_none() && job_identity.is_none()
        {
            return Ok(None);
        }
        let hello = python
            .as_ref()
            .map(|b| b.hello().clone())
            .unwrap_or_else(|| json!({"hooks":[],"register_execute_options":false}));
        Ok(Some(Self {
            python,
            native,
            brief_profile,
            job_identity,
            hello,
            context: json!({"repo_root":config.target_root,"cwd":cwd,
                "invocation_id":crate::executor_execute::unique_id(),"job_id":null,"attempt_id":null}),
            token: None,
            outcome: TeardownOutcome::Uncertain,
        }))
    }
    pub fn hello(&self) -> &Value {
        &self.hello
    }
    pub fn teardown_outcome(&mut self, outcome: TeardownOutcome) {
        self.outcome = outcome;
    }
    pub fn call(
        &mut self,
        name: &str,
        args: Vec<Value>,
        options: Value,
    ) -> Result<Value, BridgeError> {
        <Self as HookClient>::call(self, name, args, options)
    }
}
impl HookClient for CommandHooks {
    fn call(&mut self, name: &str, args: Vec<Value>, options: Value) -> Result<Value, BridgeError> {
        if name == "job_identity"
            && let Some(identity) = &self.job_identity
        {
            let prompt = args
                .get(2)
                .and_then(Value::as_str)
                .ok_or(BridgeError::Protocol("identity prompt must be a string"))?;
            let dispatch = args
                .first()
                .is_some_and(|argument| argument["value"]["dispatch"] == true);
            let model = args.get(3).and_then(Value::as_str);
            return Ok(
                json!({"ok":true,"result":identity.render(dispatch, prompt, model),"handle":null}),
            );
        }
        if name == "validate_brief"
            && let Some(profile) = &self.brief_profile
        {
            let root = args
                .get(1)
                .and_then(|argument| argument["value"].as_str())
                .ok_or(BridgeError::Protocol("brief root must be a path"))?;
            let result =
                if let Some(argument) = args.first().filter(|value| value["$type"] == "path") {
                    let path = argument["value"]
                        .as_str()
                        .ok_or(BridgeError::Protocol("brief path must be UTF-8"))?;
                    profile.load(Path::new(path)).and_then(|value| {
                        profile.bound_text(
                            value["expanded_goal"].as_str().unwrap_or_default(),
                            Path::new(root),
                        )?;
                        Ok(value)
                    })
                } else {
                    let text = args
                        .first()
                        .and_then(Value::as_str)
                        .ok_or(BridgeError::Protocol("brief text must be a string"))?;
                    profile
                        .bound_text(text, Path::new(root))
                        .map(|()| Value::Null)
                };
            return Ok(match result {
                Ok(value) => json!({"ok":true,"result":value,"handle":null}),
                Err(error) => {
                    json!({"ok":false,"error":{"type":error.kind,"message":error.message}})
                }
            });
        }
        if let Some(native) = self.native.as_mut() {
            if native.serves("writer_scope") {
                match name {
                    "writer_scope" => {
                        return Ok(json!({"ok":true,"handle":"native-writer","result":null}));
                    }
                    "writer_scope.enter" => {
                        if self.token.is_some() {
                            return Err(BridgeError::Protocol("writer already entered"));
                        }
                        let reply = native.call("writer_enter", self.context.clone())?;
                        if reply["ok"] == true {
                            let token = reply["result"]["token"]
                                .as_str()
                                .filter(|s| !s.is_empty())
                                .ok_or(BridgeError::Protocol(
                                    "writer_enter requires opaque token",
                                ))?;
                            self.token = Some(token.to_owned());
                        }
                        return Ok(reply);
                    }
                    "writer_scope.exit" => {
                        let Some(token) = self.token.take() else {
                            return Err(BridgeError::Protocol("writer not entered"));
                        };
                        let mut params = self.context.clone();
                        params["token"] = json!(token);
                        params["outcome"] = json!(self.outcome.as_str());
                        return native.call("writer_exit", params);
                    }
                    _ => (),
                }
            }
            if name == "on_job_event" && native.serves(name) {
                let event = args
                    .first()
                    .and_then(Value::as_str)
                    .ok_or(BridgeError::Protocol("event name must be a string"))?;
                let payload = args
                    .get(1)
                    .filter(|p| p.is_object())
                    .ok_or(BridgeError::Protocol("event payload must be an object"))?;
                let mut params = self.context.clone();
                params["event"] = json!(event);
                params["payload"] = native_value(payload);
                params["job_id"] = payload["job_id"].clone();
                params["attempt_id"] = payload["dispatch_id"].clone();
                return native.call(name, params);
            }
        }
        if let Some(python) = self.python.as_mut() {
            return python.call(name, args, options);
        }
        Ok(json!({"ok":true,"result":null,"handle":null,"args":args}))
    }
}
impl Drop for CommandHooks {
    fn drop(&mut self) {
        if self.token.is_some() {
            self.outcome = TeardownOutcome::Uncertain;
            let _ = self.call("writer_scope.exit", vec![], json!({}));
        }
    }
}

// Native messages contain plain JSON, never Python path/namespace wrappers.
fn native_value(value: &Value) -> Value {
    if matches!(value["$type"].as_str(), Some("path" | "namespace")) {
        return native_value(&value["value"]);
    }
    match value {
        Value::Array(items) => Value::Array(items.iter().map(native_value).collect()),
        Value::Object(fields) => Value::Object(
            fields
                .iter()
                .map(|(key, value)| (key.clone(), native_value(value)))
                .collect(),
        ),
        _ => value.clone(),
    }
}
