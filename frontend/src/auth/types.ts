export type AuthRole = 'admin' | 'member';

export type ProductPermission<Role extends string = string> = {
  role: Role;
  scope_ids: string[];
};

export type AuthPermissions = {
  work?: ProductPermission<'manager' | 'worker' | 'reviewer'>;
  knowledge?: ProductPermission<'manager' | 'writer' | 'reader'>;
  code?: ProductPermission<'manager' | 'writer' | 'reader'>;
};

export type IdentityUser = {
  id: string;
  email: string;
  name: string;
  role: AuthRole;
  active: boolean;
  permissions: AuthPermissions;
  credential_type?: 'local' | 'sso';
  permissions_source?: 'manual' | 'sso' | 'scim';
};

export type IdentitySession = {
  user: IdentityUser;
  csrf_token: string;
  expires_at: string;
  recovery_codes?: string[];
  authentication?: { method: 'password' | 'oidc'; provider_name?: string };
};

export type IdentitySessionRecord = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
};

export type PersonalAccessToken = {
  id: string;
  name: string;
  prefix: string;
  products: ProductKey[];
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

export type IdentityInvitation = {
  invitation_code: string;
  expires_at: string;
  mail_queued?: boolean;
};

export type IdentityStatus = {
  setup_required: boolean;
  sso?: { enabled: boolean; display_name: string; login_policy: 'password_and_sso' | 'sso_only'; configured: boolean; public_origin: string };
};

export type IdentitySsoSettings = {
  revision: number;
  enabled: boolean;
  display_name: string;
  issuer_url: string;
  client_id: string;
  client_secret_configured: boolean;
  redirect_uri: string;
  scopes: string[];
  allowed_email_domains: string[];
  email_claim: string;
  require_email_verified: boolean;
  groups_claim: string;
  provisioning: 'invited_only' | 'jit';
  default_permissions: AuthPermissions;
  group_mappings: Array<{ group: string; permissions: AuthPermissions }>;
  login_policy: 'password_and_sso' | 'sso_only';
  required_acr: string[];
  required_amr: string[];
};

export type IdentitySsoSettingsWrite = Omit<IdentitySsoSettings, 'client_secret_configured' | 'redirect_uri'> & { client_secret?: string };

export type IdentitySsoTestResult = {
  status: 'ok';
  issuer: string;
  authorization_endpoint: string;
  redirect_uri: string;
  supported_algs: string[];
};

export type IdentitySsoLink = {
  id: string;
  user_id: string;
  issuer: string;
  subject: string;
  managed_permissions: boolean;
};

export type IdentityAuditEvent = {
  id: string;
  created_at: string;
  actor_id: string | null;
  user_id: string | null;
  action: string;
  details: Record<string, unknown>;
};

export type ProductScope = {
  id: string;
  key?: string;
  name: string;
};

export type ProductKey = keyof AuthPermissions;
