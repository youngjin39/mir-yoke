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
    instruction: Option<(std::path::PathBuf, String)>,
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
        let mut hello = python
            .as_ref()
            .map(|b| b.hello().clone())
            .unwrap_or_else(|| json!({"hooks":[],"register_execute_options":false}));
        if brief_profile.as_ref().is_some_and(|profile| {
            profile.capabilities() || profile.execution() || profile.packet()
        }) && let Some(hooks) = hello["hooks"].as_array_mut()
        {
            hooks.push(json!("render_brief"));
        }
        Ok(Some(Self {
            python,
            native,
            brief_profile,
            job_identity,
            instruction: None,
            hello,
            context: json!({"repo_root":config.target_root,"cwd":cwd,
                "invocation_id":crate::executor_execute::unique_id(),"job_id":null,"attempt_id":null}),
            token: None,
            outcome: TeardownOutcome::Uncertain,
        }))
    }
    /// Supply the invocation instruction explicitly; rendering consumes it once.
    pub(crate) fn bind_instruction(
        &mut self,
        root: &Path,
        cwd: &Path,
        args: &Value,
        resumed: Option<Vec<String>>,
    ) -> Result<(), crate::executor_target_policy::PolicyFailure> {
        if !self.brief_profile.as_ref().is_some_and(|p| p.execution())
            || args["dispatch"] != true
            || args["dispatch_brief"].is_null()
        {
            return Ok(());
        }
        let raw = crate::executor_execute::value_path(&args["dispatch_brief"], cwd);
        let path = crate::executor_admission::resolved(&raw, cwd)
            .map_err(|e| crate::executor_brief_profile::io_failure(e, &raw))?;
        let fail = |message: String| crate::executor_target_policy::PolicyFailure {
            kind: "ValueError".into(),
            message,
            stderr: None,
        };
        let argv = if let Some(argv) = resumed {
            argv
        } else if args["codex_args"].is_null() && args["codex_args_file"].is_null() {
            vec![]
        } else {
            if !args["codex_args"].is_null() && !args["codex_args_file"].is_null() {
                return Err(fail(
                    "exactly one of --codex-args or --codex-args-file must be provided".into(),
                ));
            }
            let local =
                crate::executor_local::LocalConfig::load(root).map_err(|e| fail(e.to_string()))?;
            // Read the file with Python's exception text before the common argv
            // resolver; this instruction selection is outside the brief wrapper.
            if !args["codex_args_file"].is_null() {
                let file = crate::executor_execute::value_path(&args["codex_args_file"], cwd);
                let bytes = std::fs::read(&file)
                    .map_err(|e| crate::executor_brief_profile::io_failure(e, &file))?;
                local
                    .validate_input_size(bytes.len() as u64)
                    .map_err(|e| fail(e.to_string()))?;
                let text = String::from_utf8(bytes).map_err(|e| {
                    let error = crate::executor_local::Error::Unicode(e);
                    crate::executor_target_policy::PolicyFailure {
                        kind: error.kind().into(),
                        message: error.to_string(),
                        stderr: None,
                    }
                })?;
                vec![text.replace("\r\n", "\n").replace('\r', "\n")]
            } else {
                crate::executor_execute::resolve_args(args, cwd, &local).map_err(fail)?
            }
        };
        let instruction = crate::executor_execute::prompt(&argv);
        // Empty prompts use the goal at render time, matching _active_instruction.
        self.instruction = Some((path, instruction));
        Ok(())
    }
    pub fn hello(&self) -> &Value {
        &self.hello
    }
    pub fn python_exports(&self, hook: &str) -> bool {
        self.python.as_ref().is_some_and(|bridge| {
            bridge.hello()["hooks"]
                .as_array()
                .is_some_and(|hooks| hooks.iter().any(|value| value == hook))
        })
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
        if name == "bridge.target_agent" && self.brief_profile.as_ref().is_some_and(|p| p.packet())
        {
            let target = args
                .first()
                .map(|packet| packet["target_agent"].clone())
                .unwrap_or(Value::Null);
            if !target.is_null()
                && target.as_str().is_none_or(|text| {
                    text.trim_matches(crate::executor_brief_authority::python_space)
                        .is_empty()
                })
            {
                return Ok(
                    json!({"ok":false,"error":{"type":"ValueError","message":"DispatchBrief target_agent must be a non-empty string"}}),
                );
            }
            return Ok(json!({"ok":true,"result":target,"handle":null}));
        }
        if name == "job_identity"
            && let Some(identity) = &self.job_identity
        {
            if let Some(result) = identity.render_scope(
                &args
                    .first()
                    .map(|arg| arg["value"].clone())
                    .unwrap_or(Value::Null),
            ) {
                return Ok(json!({"ok":true,"result":result,"handle":null}));
            }
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
                        if profile.capabilities() {
                            crate::executor_brief_authority::authorize(Path::new(root), &value)?;
                        }
                        if profile.packet() {
                            let mut packet = crate::executor_development_packet::validate(
                                value["expanded_goal"].as_str().unwrap_or_default(),
                                Path::new(root),
                            )?;
                            if let Some(fields) = packet.as_object_mut() {
                                fields
                                    .entry("target_agent")
                                    .or_insert_with(|| value["target_agent"].clone());
                            }
                            Ok(packet)
                        } else {
                            Ok(value)
                        }
                    })
                } else {
                    let text = args
                        .first()
                        .and_then(Value::as_str)
                        .ok_or(BridgeError::Protocol("brief text must be a string"))?;
                    if profile.packet() {
                        crate::executor_development_packet::validate(text, Path::new(root))
                    } else {
                        profile
                            .bound_text(text, Path::new(root))
                            .map(|()| Value::Null)
                    }
                };
            return Ok(match result {
                Ok(value) => json!({"ok":true,"result":value,"handle":null}),
                Err(error) => {
                    json!({"ok":false,"error":{"type":error.kind,"message":error.message}})
                }
            });
        }
        if name == "render_brief" && self.brief_profile.as_ref().is_some_and(|p| p.packet()) {
            let result = args.first().map(crate::executor_development_packet::render);
            return Ok(json!({"ok":true,"result":result,"handle":null}));
        }
        if name == "render_brief" && self.brief_profile.as_ref().is_some_and(|p| p.execution()) {
            let Some(brief) = args.first().filter(|v| !v.is_null()) else {
                return Ok(json!({"ok":true,"result":null,"handle":null}));
            };
            let root = args
                .get(1)
                .and_then(|v| v["value"].as_str())
                .unwrap_or_default();
            let raw = Path::new(root).join(brief["resume_state_ref"].as_str().unwrap_or_default());
            let path = crate::executor_admission::resolved(&raw, Path::new(root))
                .map_err(|_| BridgeError::Protocol("invalid brief render path"))?;
            let instruction = if self
                .instruction
                .as_ref()
                .is_some_and(|(key, _)| *key == path)
            {
                self.instruction.take().map(|(_, text)| text)
            } else {
                None
            };
            let result = crate::executor_brief_execution::render(
                brief,
                instruction.as_deref().filter(|s| !s.is_empty()),
            )
            .map_err(|_| BridgeError::Protocol("invalid brief rendering"))?;
            return Ok(json!({"ok":true,"result":result,"handle":null}));
        }
        if name == "render_brief"
            && self
                .brief_profile
                .as_ref()
                .is_some_and(|profile| profile.capabilities())
        {
            let result = args
                .first()
                .filter(|value| !value.is_null())
                .map(crate::executor_brief_authority::render);
            return Ok(json!({"ok":true,"result":result,"handle":null}));
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

#[cfg(test)]
mod execution_tests {
    use super::*;

    #[test]
    fn instruction_is_consumed_once_and_null_does_not_consume() {
        let root = std::env::current_dir().unwrap();
        let profile =
            crate::executor_brief_profile::BriefProfile::parse(&json!({"name":"execution_v1"}))
                .unwrap();
        let golden: Value =
            serde_json::from_str(include_str!("../tests/fixtures/executor_smd_profile.json"))
                .unwrap();
        let brief = profile
            .validate_bytes(golden["cases"][0]["text"].as_str().unwrap().as_bytes())
            .unwrap();
        let target = root.join(brief["resume_state_ref"].as_str().unwrap());
        let target = crate::executor_admission::resolved(&target, &root).unwrap();
        let mut hooks = CommandHooks {
            python: None,
            native: None,
            hello: json!({}),
            context: json!({}),
            token: None,
            outcome: TeardownOutcome::Clean,
            brief_profile: Some(profile),
            job_identity: None,
            instruction: Some((target, "  active café 漢字 😀  ".into())),
        };
        let path = json!({"$type":"path","value":root});
        assert_eq!(
            hooks
                .call("render_brief", vec![Value::Null, path.clone()], json!({}))
                .unwrap()["result"],
            Value::Null
        );
        let first = hooks
            .call("render_brief", vec![brief.clone(), path.clone()], json!({}))
            .unwrap();
        assert_eq!(
            first["result"],
            crate::executor_brief_execution::render(&brief, Some("active café 漢字 😀")).unwrap()
        );
        assert!(hooks.instruction.is_none());
        let second = hooks
            .call("render_brief", vec![brief.clone(), path], json!({}))
            .unwrap();
        assert_eq!(
            second["result"],
            crate::executor_brief_execution::render(&brief, None).unwrap()
        );
        assert_ne!(first["result"], second["result"]);
    }
}
