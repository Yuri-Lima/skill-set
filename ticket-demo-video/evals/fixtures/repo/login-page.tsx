export default function SignInPage() {
  return (
    <form action="/signin">
      <input id="email" name="email" />
      <input id="password" name="password" type="password" />
      <button type="submit">Sign in</button>
    </form>
  );
}
