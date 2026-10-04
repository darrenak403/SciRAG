export default function AuthLayout({ children }: LayoutProps<"/">) {
  return <main className="flex min-h-full items-center justify-center p-6">{children}</main>;
}
