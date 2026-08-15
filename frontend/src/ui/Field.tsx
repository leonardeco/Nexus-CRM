import { Eye, EyeOff } from "lucide-react";
import {
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useId,
  useState,
} from "react";

type FieldProps = {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: ReactNode;
};

export function Field({ label, required = false, error, hint, children }: FieldProps) {
  return (
    <div className="field">
      <span className="field-label">
        {label}
        {required ? (
          <span className="req" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </span>
      {children}
      {hint ? <span className="muted">{hint}</span> : null}
      {error ? (
        <span className="field-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  label: string;
  error?: string;
  hint?: string;
};

export function TextField({
  label,
  error,
  hint,
  required,
  type = "text",
  ...props
}: TextFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [hint ? hintId : undefined, error ? errorId : undefined]
    .filter(Boolean)
    .join(" ") || undefined;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
        {required ? (
          <span className="req" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </label>
      <input
        id={id}
        className="input"
        type={type}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...props}
      />
      {hint ? (
        <span id={hintId} className="muted">
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={errorId} className="field-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

type PasswordFieldProps = Omit<TextFieldProps, "type">;

export function PasswordField({
  label,
  error,
  hint,
  required,
  ...props
}: PasswordFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [hint ? hintId : undefined, error ? errorId : undefined]
    .filter(Boolean)
    .join(" ") || undefined;
  const [visible, setVisible] = useState(false);
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
        {required ? (
          <span className="req" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </label>
      <div className="password-wrap">
        <input
          id={id}
          className="input"
          type={visible ? "text" : "password"}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...props}
        />
        <button
          type="button"
          className="password-toggle"
          onClick={() => setVisible((value) => !value)}
          aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
        >
          {visible ? <EyeOff size={24} aria-hidden="true" /> : <Eye size={24} aria-hidden="true" />}
        </button>
      </div>
      {hint ? (
        <span id={hintId} className="muted">
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={errorId} className="field-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

type SelectFieldProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> & {
  label: string;
  error?: string;
  children: ReactNode;
};

export function SelectField({
  label,
  error,
  required,
  children,
  ...props
}: SelectFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
        {required ? (
          <span className="req" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </label>
      <select
        id={id}
        className="select"
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        {...props}
      >
        {children}
      </select>
      {error ? (
        <span id={errorId} className="field-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

type TextAreaFieldProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> & {
  label: string;
  error?: string;
};

export function TextAreaField({
  label,
  error,
  required,
  ...props
}: TextAreaFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
        {required ? (
          <span className="req" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </label>
      <textarea
        id={id}
        className="textarea"
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        {...props}
      />
      {error ? (
        <span id={errorId} className="field-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

export function focusFirstInvalid(form: HTMLFormElement): void {
  const invalid = form.querySelector<HTMLElement>(":invalid");
  invalid?.focus();
}

export function passwordPolicyError(value: string): string | undefined {
  if (value.length < 10) {
    return "La contraseña debe tener al menos 10 caracteres.";
  }
  if (!/[A-Z]/.test(value)) {
    return "Incluye al menos una letra mayúscula.";
  }
  if (!/[a-z]/.test(value)) {
    return "Incluye al menos una letra minúscula.";
  }
  if (!/[0-9]/.test(value)) {
    return "Incluye al menos un dígito.";
  }
  return undefined;
}
