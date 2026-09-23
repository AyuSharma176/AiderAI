export interface User {
  id: string;
  email: string;
  name: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id?: string;
}
