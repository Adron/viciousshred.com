# Generates WordPress-compatible archive pages, paginated like WordPress (/page/N/):
#   /category/<slug>/   /tag/<slug>/   /author/adron/   /YYYY/   /YYYY/MM/   /YYYY/MM/DD/
# Category/tag slugs come from _data/wp_taxonomy.yml (exported from WordPress) so the
# old URLs keep working; anything new falls back to a WordPress-style slug.
module ViciousShred
  class ArchivePage < Jekyll::PageWithoutAFile
    def initialize(site, dir, data)
      super(site, site.source, dir, "index.html")
      self.content = ""
      self.data = { "layout" => "archive" }.merge(data)
    end
  end

  class ArchiveGenerator < Jekyll::Generator
    safe true
    priority :low

    def self.wp_slug(name)
      Jekyll::Utils.slugify(name.to_s.gsub("&", " "), mode: "latin")
    end

    def self.norm(name)
      name.to_s.dup.force_encoding("UTF-8").unicode_normalize(:nfc)
    end

    # Exact WordPress slug for a category/tag name, or a WordPress-style slug for new terms.
    def self.term_slug(site, name, kind)
      map = site.config[kind == "tag" ? "tag_slugs" : "category_slugs"] || {}
      map[norm(name)] || wp_slug(name)
    end

    # One archive, split into WordPress-sized pages: dir/, dir/page/2/, ...
    def add_archive(site, dir, title, posts)
      per = site.config["paginate"] || 10
      posts = posts.uniq.sort_by(&:date).reverse
      chunks = posts.each_slice(per).to_a
      chunks.each_with_index do |chunk, i|
        n = i + 1
        page_dir = n == 1 ? dir : "#{dir}/page/#{n}"
        site.pages << ArchivePage.new(site, page_dir, {
          "title" => n == 1 ? title : "#{title} – Page #{n}",
          "archive_title" => title,
          "posts" => chunk,
          "previous_page_path" => n == 1 ? nil : (n == 2 ? "/#{dir}/" : "/#{dir}/page/#{n - 1}/"),
          "next_page_path" => n < chunks.size ? "/#{dir}/page/#{n + 1}/" : nil,
        })
      end
    end

    def generate(site)
      tax = site.data["wp_taxonomy"] || {}
      site.config["category_slugs"] = (tax["categories"] || {}).transform_keys { |k| self.class.norm(k) }
      site.config["tag_slugs"] = (tax["tags"] || {}).transform_keys { |k| self.class.norm(k) }

      { "category" => site.categories, "tag" => site.tags }.each do |kind, index|
        by_slug = Hash.new { |h, k| h[k] = { "name" => nil, "posts" => [] } }
        index.each do |name, posts|
          slug = self.class.term_slug(site, name, kind)
          next if slug.empty?
          by_slug[slug]["name"] ||= name
          by_slug[slug]["posts"].concat(posts)
        end
        # Non-ASCII WordPress slugs are stored percent-encoded; the output directory needs the
        # decoded name so the encoded URL resolves to it.
        by_slug.each do |slug, t|
          add_archive(site, "#{kind}/#{URI.decode_www_form_component(slug)}", t["name"], t["posts"])
        end
      end

      # Old WordPress URLs that redirect elsewhere (_data/redirects.yml: "/old/path/": "/new/path/").
      (site.data["redirects"] || {}).each do |from, to|
        page = Jekyll::PageWithoutAFile.new(site, site.source, from.to_s.sub(%r{^/}, ""), "index.html")
        page.content = ""
        page.data = { "layout" => "redirect", "redirect_to" => to, "sitemap" => false }
        site.pages << page
      end

      # Single-author blog: WordPress's author archive lists every post.
      add_archive(site, "author/adron", "Adron", site.posts.docs)

      by = Hash.new { |h, k| h[k] = [] }
      site.posts.docs.each do |post|
        d = post.date
        by[[d.strftime("%Y")]] << post
        by[[d.strftime("%Y"), d.strftime("%m")]] << post
        by[[d.strftime("%Y"), d.strftime("%m"), d.strftime("%d")]] << post
      end
      by.each do |parts, posts|
        date = Time.new(*parts.map(&:to_i))
        title = case parts.size
                when 1 then parts[0]
                when 2 then date.strftime("%B %Y")
                else date.strftime("%B %-d, %Y")
                end
        add_archive(site, parts.join("/"), title, posts)
      end
    end
  end
end

module ViciousShred
  module Filters
    # {{ name | term_slug: "category" }} -> slug used in /category/<slug>/
    def term_slug(name, kind = "category")
      ArchiveGenerator.term_slug(@context.registers[:site], name, kind)
    end
  end
end
Liquid::Template.register_filter(ViciousShred::Filters)

# WordPress served its RSS feed at /feed/. Keep that URL alive alongside /feed.xml.
Jekyll::Hooks.register :site, :post_write do |site|
  src = File.join(site.dest, "feed.xml")
  if File.exist?(src)
    dir = File.join(site.dest, "feed")
    FileUtils.mkdir_p(dir)
    FileUtils.cp(src, File.join(dir, "index.html"))
  end
end
