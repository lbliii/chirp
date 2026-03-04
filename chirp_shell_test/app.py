from chirp import App, AppConfig

config = AppConfig(template_dir="pages", debug=True)
app = App(config=config)
app.mount_pages("pages")

if __name__ == "__main__":
    app.run()
